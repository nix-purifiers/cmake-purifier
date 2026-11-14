{ pkgs }:
let
  nativeGradle = pkgs.gradle_8.unwrapped;
in
pkgs.runCommand "thrift-java-native-gradle-wrapper"
  (
    {
      nativeBuildInputs = [
        nativeGradle
        pkgs.jdk17_headless
      ];
    }
    // pkgs.lib.optionalAttrs pkgs.stdenv.buildPlatform.isDarwin {
      # Gradle uses a local socket for native file-lock contention handling.
      __darwinAllowLocalNetworking = true;
      # Java's dual-stack sockets keep Gradle from connecting to its daemon
      # inside the Darwin sandbox.
      env.JAVA_TOOL_OPTIONS = "-Djava.net.preferIPv4Stack=true";
    }
  )
  ''
    export HOME="$TMPDIR/home" GRADLE_USER_HOME="$TMPDIR/gradle-home" JAVA_HOME=${pkgs.jdk17_headless}
    mkdir -p "$HOME" project
    cd project
    echo "rootProject.name='thrift-sdk-wrapper'" > settings.gradle
    gradle --offline --no-daemon --console=plain wrapper --gradle-distribution-url ${pkgs.lib.escapeShellArg (builtins.head nativeGradle.src.urls)} --gradle-distribution-sha256-sum "$(sha256sum ${nativeGradle.src} | cut -d ' ' -f1)" --no-validate-url
    mkdir -p "$out"
    cp -r gradle gradlew gradlew.bat "$out/"
  ''
