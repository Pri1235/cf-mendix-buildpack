import logging
import os
import json
import subprocess
import shutil

from buildpack import util
from buildpack.infrastructure import database

NAMESPACE = "metering"
BINARY = "sidecar.py"
SIDECAR_DIR = os.path.join("/home/vcap/app", NAMESPACE)
SIDECAR_CONFIG_FILE = "conf.json"
CUSTOM_SIDECAR_SOURCE = "custom-sidecar"


def _copy_custom_sidecar(buildpack_dir, build_path):
    """Copy custom sidecar files to the build directory"""
    source_dir = os.path.join(buildpack_dir, CUSTOM_SIDECAR_SOURCE)
    target_dir = os.path.join(build_path, NAMESPACE)
    
    if os.path.exists(source_dir):
        logging.info(f"Copying custom sidecar from {source_dir} to {target_dir}")
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
        
        # Make the Python script executable
        sidecar_script = os.path.join(target_dir, BINARY)
        if os.path.exists(sidecar_script):
            os.chmod(sidecar_script, 0o755)
        return True
    else:
        logging.error(f"Custom sidecar source directory not found: {source_dir}")
        return False


def _download(buildpack_dir, build_path, cache_dir):
    # Use custom sidecar instead of downloading from dependencies
    return _copy_custom_sidecar(buildpack_dir, build_path)


def _is_usage_metering_enabled():
    if "MXUMS_LICENSESERVER_URL" in os.environ:
        return True


def _get_project_id(file_path):
    try:
        with open(file_path) as file_handle:
            data = json.loads(file_handle.read())
            return data["ProjectID"]
    except IOError as ioerror:
        raise Exception(
            f"Error while trying to get the ProjectID. Reason: '{ioerror}'"
        ) from ioerror


def write_file(output_file_path, content):
    if output_file_path is None:
        print(content)
    else:
        try:
            with open(output_file_path, "w") as f:
                json.dump(content, f)
        except Exception as exception:
            raise Exception(
                f"Error while trying to write the configuration to a file. Reason: '{exception}'"  # noqa: C0301
            ) from exception


def _set_up_environment():
    env = dict(os.environ.copy())
    
    # Set up VCAP_SERVICES for your HANA sidecar
    if "VCAP_SERVICES" in os.environ:
        env["VCAP_SERVICES"] = os.environ["VCAP_SERVICES"]
    
    # Keep existing metering environment variables for compatibility
    if "MXRUNTIME_License.SubscriptionSecret" in os.environ:
        env["MXUMS_SUBSCRIPTION_SECRET"] = os.environ[
            "MXRUNTIME_License.SubscriptionSecret"
        ]
    if "MXRUNTIME_License.LicenseServerURL" in os.environ:
        env["MXUMS_LICENSESERVER_URL"] = os.environ[
            "MXRUNTIME_License.LicenseServerURL"
        ]
    if "MXRUNTIME_License.EnvironmentName" in os.environ:
        env["MXUMS_ENVIRONMENT_NAME"] = os.environ[
            "MXRUNTIME_License.EnvironmentName"
        ]
    
    # Add database configuration for backwards compatibility
    dbconfig = database.get_config()
    if dbconfig:
        env["MXUMS_DB_CONNECTION_URL"] = (
            f"postgres://{dbconfig['DatabaseUserName']}:"
            f"{dbconfig['DatabasePassword']}@"
            f"{dbconfig['DatabaseHost']}/"
            f"{dbconfig['DatabaseName']}"
        )
    
    # Set project ID if config file exists
    config_file = os.path.join(SIDECAR_DIR, SIDECAR_CONFIG_FILE)
    if os.path.exists(config_file):
        try:
            project_id = _get_project_id(config_file)
            env["MXUMS_PROJECT_ID"] = project_id
        except Exception as e:
            logging.warning(f"Could not read project ID: {e}")
    
    return env


def _is_sidecar_installed():
    sidecar_script = os.path.join(SIDECAR_DIR, BINARY)
    vendor_dir = os.path.join(SIDECAR_DIR, "vendor")
    
    if os.path.exists(sidecar_script):
        if os.path.exists(vendor_dir):
            logging.info("Custom Python sidecar and dependencies found")
            return True
        else:
            logging.info("Custom Python sidecar found but vendor dependencies missing")
    else:
        logging.info("Custom Python sidecar not found")
    return False


def stage(buildpack_path, build_path, cache_dir):
    try:
        if _is_usage_metering_enabled():
            logging.info("Usage metering is enabled - deploying custom sidecar")
            success = _download(buildpack_path, build_path, cache_dir)
            
            if success:
                # Create project ID config if we can get it from model metadata
                try:
                    project_id = _get_project_id(
                        os.path.join(build_path, "model", "metadata.json")
                    )
                    config = {"ProjectID": project_id}

                    logging.debug("Writing metering sidecar configuration file...")
                    write_file(
                        os.path.join(build_path, NAMESPACE, SIDECAR_CONFIG_FILE),
                        config,
                    )
                except Exception as e:
                    logging.warning(f"Could not create project ID config: {e}")
            else:
                logging.error("Failed to copy custom sidecar")
        else:
            logging.info("Usage metering is NOT enabled")
    except Exception as e:
        logging.info(
            f"Encountered an exception while staging the metering sidecar: {e}. "
            "This is nothing to worry about."
        )


def run():
    try:
        if _is_usage_metering_enabled() and _is_sidecar_installed():
            logging.info("Starting custom Python sidecar")
            
            # Run the Python sidecar script
            sidecar_script = os.path.join(SIDECAR_DIR, BINARY)
            
            # Use python3 to run the script
            subprocess.Popen(
                ["python3", sidecar_script],
                env=_set_up_environment(),
                cwd=SIDECAR_DIR,  # Set working directory to sidecar directory
            )
    except Exception as e:
        logging.info(
            f"Encountered an exception while starting the metering sidecar: {e}. "
            "This is nothing to worry about."
        )
