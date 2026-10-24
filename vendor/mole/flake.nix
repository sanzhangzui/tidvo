{
  description = "Mole - Deep clean and optimize your Mac";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";
  };

  outputs =
    inputs:
    let
      inherit (inputs.nixpkgs) lib;
      darwinPackages = lib.getAttrs [
        "aarch64-darwin"
        "x86_64-darwin"
      ] inputs.nixpkgs.legacyPackages;
    in
    {
      # for users who want to build mole with their own nixpkgs to keep the system closure small
      overlays.default = import ./overlay.nix;

      formatter = builtins.mapAttrs (_system: pkgs: pkgs.callPackage ./formatter.nix { }) darwinPackages;

      packages = builtins.mapAttrs (system: pkgs: {
        mole = pkgs.callPackage ./package.nix { };
        default = inputs.self.packages.${system}.mole;
      }) darwinPackages;

      checks = builtins.mapAttrs (
        system: _pkgs:
        inputs.self.packages.${system}
        // {
          # go.mod names toolchain go1.26.10, which goimports would try to
          # download; the build sandbox has no network, so use nixpkgs' Go.
          formatting = (inputs.self.formatter.${system}.check inputs.self).overrideAttrs (old: {
            env = (old.env or { }) // {
              GOTOOLCHAIN = "local";
            };
          });
        }
      ) darwinPackages;

      apps = builtins.mapAttrs (system: _pkgs: {
        mole = {
          type = "app";
          program = lib.getExe inputs.self.packages.${system}.mole;
          meta.description = "Deep clean and optimize your Mac";
        };
        mo = {
          type = "app";
          program = lib.getExe' inputs.self.packages.${system}.mole "mo";
          meta.description = "Mole CLI alias";
        };
        default = inputs.self.apps.${system}.mole;
      }) darwinPackages;

      devShells = builtins.mapAttrs (system: pkgs: {
        default = pkgs.mkShell {
          inputsFrom = [ inputs.self.packages.${system}.mole ];

          packages = with pkgs; [
            # Go linters
            golangci-lint
            gotools # provides goimports

            # Shell scripting and linting
            bash
            shellcheck
            shfmt

            # Test suites and execution
            bats
            parallel # parallel bats execution

            # Build and development utilities (gnumake comes with stdenv)
            coreutils-prefixed # provides gtimeout without shadowing macOS BSD tools
            python3 # required by audit scripts in scripts/check.sh
            fd # optional test dependency (installer_fd.bats)
            zip # optional test dependency (installer_zip.bats)
            unzip
            git
            inputs.self.formatter.${system} # run all formatters/linters with `treefmt`
          ];
        };
      }) darwinPackages;
    };
}
