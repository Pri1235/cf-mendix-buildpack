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
        
        # Create target directory if it doesn't exist
        os.makedirs(target_dir, exist_ok=True)
        
        # Copy all files and directories from source to target
        for item in os.listdir(source_dir):
            source_item = os.path.join(source_dir, item)
            target_item = os.path.join(target_dir, item)
            
            if os.path.isdir(source_item):
                shutil.copytree(source_item, target_item, dirs_exist_ok=True)
                logging.info(f"Copied directory: {item}")
            else:
                shutil.copy2(source_item, target_item)
                logging.info(f"Copied file: {item}")
        
        # Make the Python script executable
        sidecar_script = os.path.join(target_dir, BINARY)
        if os.path.exists(sidecar_script):
            os.chmod(sidecar_script, 0o755)
            logging.info(f"Made {BINARY} executable")
        
        # Verify vendor directory was copied
        vendor_dir = os.path.join(target_dir, "vendor")
        if os.path.exists(vendor_dir):
            logging.info(f"Vendor directory copied successfully: {vendor_dir}")
            # List vendor contents for debugging
            vendor_contents = os.listdir(vendor_dir)
            logging.info(f"Vendor directory contents: {vendor_contents}")
        else:
            logging.error(f"Vendor directory not found after copying: {vendor_dir}")
            
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
    
    logging.info(f"Checking sidecar installation:")
    logging.info(f"  Script path: {sidecar_script}")
    logging.info(f"  Vendor path: {vendor_dir}")
    logging.info(f"  Script exists: {os.path.exists(sidecar_script)}")
    logging.info(f"  Vendor exists: {os.path.exists(vendor_dir)}")
    
    if os.path.exists(sidecar_script):
        if os.path.exists(vendor_dir):
            # List vendor contents for debugging
            try:
                vendor_contents = os.listdir(vendor_dir)
                logging.info(f"Vendor directory contents: {vendor_contents}")
            except Exception as e:
                logging.error(f"Error listing vendor directory: {e}")
            
            logging.info("Custom Python sidecar and dependencies found")
            return True
        else:
            logging.error("Custom Python sidecar found but vendor dependencies missing")
            # List what's actually in the sidecar directory
            try:
                sidecar_contents = os.listdir(SIDECAR_DIR)
                logging.info(f"Sidecar directory contents: {sidecar_contents}")
            except Exception as e:
                logging.error(f"Error listing sidecar directory: {e}")
    else:
        logging.error("Custom Python sidecar not found")
        # Check if the directory exists at all
        if os.path.exists(SIDECAR_DIR):
            try:
                sidecar_contents = os.listdir(SIDECAR_DIR)
                logging.info(f"Sidecar directory exists but script missing. Contents: {sidecar_contents}")
            except Exception as e:
                logging.error(f"Error listing sidecar directory: {e}")
        else:
            logging.error(f"Sidecar directory does not exist: {SIDECAR_DIR}")
    
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
