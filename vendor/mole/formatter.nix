{
  lib,
  treefmt,
  nixfmt,
  statix,
  deadnix,
  shfmt,
  shellcheck,
  gotools,
}:

# Mirrors the formatting rules of scripts/check.sh.
treefmt.withConfig {
  settings = {
    tree-root-file = "flake.nix";
    on-unmatched = "info";
    formatter = {
      nixfmt = {
        command = lib.getExe nixfmt;
        includes = [ "*.nix" ];
      };
      statix = {
        command = lib.getExe statix;
        options = [ "fix" ];
        no-positional-arg-support = true;
        includes = [ "*.nix" ];
      };
      deadnix = {
        command = lib.getExe deadnix;
        options = [ "--edit" ];
        includes = [ "*.nix" ];
      };
      shfmt = {
        command = lib.getExe shfmt;
        options = [
          "-i"
          "4"
          "-ci"
          "-sr"
          "-w"
        ];
        includes = [
          "*.sh"
          "mole"
          "mo"
        ];
      };
      shellcheck = {
        command = lib.getExe shellcheck;
        includes = [
          "mole"
          "install.sh"
          "bin/*.sh"
          "lib/*/*.sh"
          "scripts/*.sh"
        ];
      };
      # Same lint scripts/test.sh runs over the test suite before the tests.
      shellcheck-tests = {
        command = lib.getExe shellcheck;
        includes = [
          "tests/*.bats"
          "tests/*.bash"
          "tests/*.sh"
          "tests/*/*.bash"
          "tests/*/*.sh"
        ];
        excludes = [ "tests/tmp-*" ];
      };
      goimports = {
        command = lib.getExe' gotools "goimports";
        options = [
          "-w"
          "-local"
          "github.com/tw93/mole"
        ];
        includes = [ "*.go" ];
      };
    };
  };
}
