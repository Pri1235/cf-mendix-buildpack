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
    
    logging.info(f"Starting sidecar copy process...")
    logging.info(f"Source directory: {source_dir}")
    logging.info(f"Target directory: {target_dir}")
    logging.info(f"Source exists: {os.path.exists(source_dir)}")
    
    if not os.path.exists(source_dir):
        logging.error(f"Custom sidecar source directory not found: {source_dir}")
        # List what's actually in the buildpack directory
        try:
            buildpack_contents = os.listdir(buildpack_dir)
            logging.info(f"Buildpack directory contents: {buildpack_contents}")
        except Exception as e:
            logging.error(f"Error listing buildpack directory: {e}")
        return False
    
    try:
        # List source directory contents
        source_contents = os.listdir(source_dir)
        logging.info(f"Source directory contents: {source_contents}")
        
        # Create target directory if it doesn't exist
        os.makedirs(target_dir, exist_ok=True)
        logging.info(f"Created target directory: {target_dir}")
        
        # Copy all files and directories from source to target
        for item in source_contents:
            if item.startswith('.'):  # Skip hidden files like .DS_Store
                logging.info(f"Skipping hidden file: {item}")
                continue
                
            source_item = os.path.join(source_dir, item)
            target_item = os.path.join(target_dir, item)
            
            logging.info(f"Processing item: {item}")
            logging.info(f"  Source: {source_item} (exists: {os.path.exists(source_item)})")
            logging.info(f"  Target: {target_item}")
            logging.info(f"  Is directory: {os.path.isdir(source_item)}")
            
            try:
                if os.path.isdir(source_item):
                    if os.path.exists(target_item):
                        logging.info(f"  Removing existing target directory")
                        shutil.rmtree(target_item)  # Remove existing directory
                    
                    logging.info(f"  Copying directory tree...")
                    shutil.copytree(source_item, target_item)
                    logging.info(f"  Successfully copied directory: {item}")
                    
                    # If it's the vendor directory, list its contents for verification
                    if item == "vendor":
                        try:
                            vendor_contents = os.listdir(target_item)
                            logging.info(f"  Vendor directory copied with contents: {vendor_contents}")
                            
                            # Check specific HANA files
                            hdbcli_path = os.path.join(target_item, "hdbcli")
                            pyhdbcli_path = os.path.join(target_item, "pyhdbcli.abi3.so")
                            logging.info(f"  hdbcli directory exists: {os.path.exists(hdbcli_path)}")
                            logging.info(f"  pyhdbcli.abi3.so exists: {os.path.exists(pyhdbcli_path)}")
                        except Exception as e:
                            logging.error(f"  Error verifying vendor contents: {e}")
                else:
                    shutil.copy2(source_item, target_item)
                    logging.info(f"  Successfully copied file: {item}")
            except Exception as e:
                logging.error(f"  CRITICAL ERROR copying {item}: {e}")
                # For vendor directory, this is critical - fail the whole operation
                if item == "vendor":
                    logging.error(f"  Vendor directory copy failed - aborting sidecar setup")
                    return False
                continue
        
        # Make the Python script executable
        sidecar_script = os.path.join(target_dir, BINARY)
        if os.path.exists(sidecar_script):
            os.chmod(sidecar_script, 0o755)
            logging.info(f"Made {BINARY} executable")
        else:
            logging.error(f"Sidecar script not found after copy: {sidecar_script}")
        
        # Verify vendor directory was copied
        vendor_dir = os.path.join(target_dir, "vendor")
        if os.path.exists(vendor_dir):
            try:
                vendor_contents = os.listdir(vendor_dir)
                logging.info(f"Vendor directory copied successfully with contents: {vendor_contents}")
            except Exception as e:
                logging.error(f"Error listing vendor directory: {e}")
        else:
            logging.error(f"Vendor directory not found after copying: {vendor_dir}")
        
        # List final target directory contents
        try:
            target_contents = os.listdir(target_dir)
            logging.info(f"Final target directory contents: {target_contents}")
        except Exception as e:
            logging.error(f"Error listing final target directory: {e}")
            
        return True
        
    except Exception as e:
        logging.error(f"Error during sidecar copy process: {e}")
        return False


def _download(buildpack_dir, build_path, cache_dir):
    # Use custom sidecar instead of downloading from dependencies
    return _copy_custom_sidecar(buildpack_dir, build_path)


def _is_usage_metering_enabled():
    # Enable custom HANA sidecar when VCAP_SERVICES contains HANA
    if "VCAP_SERVICES" in os.environ:
        try:
            vcap_services = json.loads(os.environ["VCAP_SERVICES"])
            if "hana" in vcap_services:
                logging.info("HANA service detected in VCAP_SERVICES - enabling custom sidecar")
                return True
        except Exception as e:
            logging.warning(f"Error parsing VCAP_SERVICES: {e}")
    
    # Original metering check for backwards compatibility
    if "MXUMS_LICENSESERVER_URL" in os.environ:
        logging.info("MXUMS_LICENSESERVER_URL found - enabling metering")
        return True
    
    # Check for custom environment variable
    if "ENABLE_HANA_SIDECAR" in os.environ:
        logging.info("ENABLE_HANA_SIDECAR found - enabling custom sidecar")
        return True
        
    logging.info("No metering enablement conditions met")
    return False


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
        logging.info("Checking if metering sidecar should be started...")
        metering_enabled = _is_usage_metering_enabled()
        sidecar_installed = _is_sidecar_installed()
        
        logging.info(f"Metering enabled: {metering_enabled}")
        logging.info(f"Sidecar installed: {sidecar_installed}")
        
        if metering_enabled and sidecar_installed:
            logging.info("Starting custom Python sidecar")
            
            # Run the Python sidecar script
            sidecar_script = os.path.join(SIDECAR_DIR, BINARY)
            
            # Use python3 to run the script
            process = subprocess.Popen(
                ["python3", sidecar_script],
                env=_set_up_environment(),
                cwd=SIDECAR_DIR,  # Set working directory to sidecar directory
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            logging.info(f"Custom Python sidecar started with PID: {process.pid}")
            
        elif not metering_enabled:
            logging.info("Metering not enabled - sidecar will not start")
        elif not sidecar_installed:
            logging.info("Sidecar not properly installed - cannot start")
    except Exception as e:
        logging.error(
            f"Encountered an exception while starting the metering sidecar: {e}"
        )
