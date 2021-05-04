#! /usr/bin/env node
"use strict";
const optionsDefinition = require("./options");
const { spawnSync } = require("child_process");
const path = require("path");

class MegaLinterRunner {
  async run(options) {
    // Show help ( index or for an options)
    if (options.help) {
      let outputString;
      if (options._ && options._.length) {
        outputString = optionsDefinition.generateHelpForOption(options._[0]);
      } else {
        outputString = optionsDefinition.generateHelp();
      }
      console.info(outputString);
      return { status: 0, stdout: outputString };
    }

    // Show version
    if (options.version) {
      let v = process.env.npm_package_version;
      if (!v) {
        try {
          const FindPackageJson = require("find-package-json");
          const finder = FindPackageJson(__dirname);
          v = finder.next().value.version;
        } catch (e) {
          v = "error";
        }
      }
      const outputString = `mega-linter-runner version ${v}`;
      console.log(outputString);
      return { status: 0, stdout: outputString };
    }

    // Run configuration generator
    if (options.install) {
      const yeoman = require("yeoman-environment");
      const env = yeoman.createEnv();
      env.run(path.resolve(`${__dirname}/../generators/mega-linter`));
      return { status: 0 };
    }

    // Build Mega-Linter docker image name with flavor and release version
    const release =
      options.release in ["v4", "stable"]
        ? "v4"
        : options.release == "insiders"
        ? "latest"
        : options.release
        ? options.release
        : "v4";
    const dockerImageName =
      options.flavor === "all" || options.flavor == null
        ? "nvuillam/mega-linter"
        : `nvuillam/mega-linter-${options.flavor}`;
    const dockerImage = `${dockerImageName}:${release}`;

    // Pull docker image
    if (options.nodockerpull !== true) {
      console.info(`Pulling docker image ${dockerImage} ... `);
      console.info(
        "INFO: this operation can be long during the first use of mega-linter-runner"
      );
      console.info(
        "The next runs, it will be immediate (thanks to docker cache !)"
      );
      const spawnResPull = spawnSync("docker", ["pull", dockerImage], {
        detached: false,
        stdio: "inherit",
        windowsHide: true,
        windowsVerbatimArguments: true,
      });
      // Manage case when unable to pull docker image
      if (spawnResPull.status !== 0) {
        return {
          status: 2,
          errorMsg: `Unable to pull [${dockerImage}]: \n${JSON.stringify(
            spawnResPull,
            null,
            2
          )}`,
        };
      }
    } else {
      console.log(`Skipped pull of ${dockerImage} (--nodockerpull used)`);
    }

    // Build docker run options
    const lintPath = path.resolve(options.path || ".");
    const commandArgs = [
      "run",
      "-v",
      "/var/run/docker.sock:/var/run/docker.sock:rw",
      "-v",
      `${lintPath}:/srv/megalinter-workspace:rw`,
    ];
    if (options.fix === true) {
      commandArgs.push(...["-e", "APPLY_FIXES=all"]);
    }
    if (options.debug === true) {
      commandArgs.push(...["-e", "LOG_LEVEL=DEBUG"]);
    }
    if (options.env) {
      for (const envVarEqualsValue of options.env) {
        commandArgs.push(...["-e", envVarEqualsValue]);
      }
    }
    commandArgs.push(dockerImage);

    // Call docker run
    console.log(`Command: docker ${commandArgs.join(" ")}`);
    const spawnOptions = {
      detached: false,
      cwd: process.cwd(),
      env: Object.assign({}, process.env),
      stdio: "inherit",
      windowsHide: true,
      windowsVerbatimArguments: true,
    };
    const spawnRes = spawnSync("docker", commandArgs, spawnOptions);
    return {
      status: spawnRes.status,
      stdout: spawnRes.stdout,
      stderr: spawnRes.stderr,
    };
  }
}

module.exports = { MegaLinterRunner };
