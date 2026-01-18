#!/usr/bin/env python3
"""
macOS System Cleanup Script
Analyzes and cleans up various system caches, logs, and temporary files
"""

import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import logging

# Configure logging
LOG_FILE = Path.home() / "macos_cleanup.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}\n")
    logging.info(f"HEADER: {text}")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")
    logging.info(f"SUCCESS: {text}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")
    logging.warning(text)


def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")
    logging.error(text)


def print_info(text):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ {text}{Colors.END}")
    logging.info(text)


def get_dir_size(path):
    """Get the size of a directory in bytes. Returns -1 if access denied or error."""
    if not path or not os.path.exists(path):
        return 0

    try:
        # Use -d 0 to only get the directory total, not subdirectories
        # Redirect stderr to pipe to check for permission errors
        result = subprocess.run(
            ['du', '-s', path],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Check stdout first. du usually prints the total even if some files were inaccessible.
        if result.stdout.strip():
            try:
                # du returns size in 512-byte blocks by default on macOS
                size_blocks = int(result.stdout.split()[0])
                return size_blocks * 512  # Convert to bytes
            except (ValueError, IndexError):
                pass

        # If no stdout, check for permission errors
        if "Operation not permitted" in result.stderr or "Permission denied" in result.stderr:
            logging.warning(f"du access denied for {path}, falling back to manual")
            # Do not return -1 yet, try manual walk to get partial size

    except (subprocess.TimeoutExpired, ValueError, IndexError) as e:
        logging.error(f"Error checking size for {path}: {e}")
        pass

    # Fallback: manual calculation (slower but more reliable)
    try:
        total_size = 0
        permission_error = False
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, PermissionError):
                    permission_error = True
                    pass

        if total_size > 0:
            return total_size

        if total_size == 0 and permission_error:
            return -1

        return total_size
    except Exception as e:
        logging.error(f"Fallback size calc failed for {path}: {e}")
        return 0


def format_size(bytes_size):
    """Format bytes to human-readable size"""
    if bytes_size == -1:
        return "Access Denied"
    if bytes_size == 0:
        return "Empty (0 B)"

    original = bytes_size
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def get_disk_usage():
    """Get current disk usage"""
    try:
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True,
            text=True
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            return {
                'total': parts[1],
                'used': parts[2],
                'available': parts[3],
                'percent': parts[4]
            }
    except Exception as e:
        logging.error(f"Failed to get disk usage: {e}")
    return None


def confirm_action(prompt):
    """Ask user for confirmation"""
    while True:
        response = input(f"{Colors.YELLOW}{prompt} (y/n): {Colors.END}").lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        return False


def run_command(cmd, description):
    """Run a shell command and return success status"""
    try:
        logging.info(f"Running command: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            logging.error(f"Command failed: {cmd}\nOutput: {result.stdout}\nError: {result.stderr}")
            print_error(f"Error: {result.stderr.strip()}")
            return False
        return True
    except Exception as e:
        print_error(f"Error running {description}: {str(e)}")
        logging.error(f"Exception running {description}: {e}")
        return False


class CleanupTask:
    """Represents a cleanup task"""
    def __init__(self, name, description, size_func, cleanup_func):
        self.name = name
        self.description = description
        self.size_func = size_func
        self.cleanup_func = cleanup_func
        self.size = 0

    def calculate_size(self):
        """Calculate the size of files to be cleaned"""
        try:
            self.size = self.size_func()
        except Exception as e:
            print_error(f"Error calculating size for {self.name}: {str(e)}")
            logging.error(f"Size calc error for {self.name}: {e}")
            self.size = 0

    def execute(self):
        """Execute the cleanup"""
        try:
            return self.cleanup_func()
        except Exception as e:
            print_error(f"Error during {self.name}: {str(e)}")
            logging.error(f"Cleanup error for {self.name}: {e}")
            return False


def get_path_via_command(cmd_args):
    """Helper to get path from command output"""
    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logging.debug(f"Command {' '.join(cmd_args)} failed: {e}")
    return None

# --- Cleanup Functions ---

def cleanup_homebrew():
    """Clean up Homebrew"""
    if not shutil.which('brew'):
        return True

    commands = [
        ("brew cleanup -s", "Cleaning Homebrew cache and old versions"),
        ("brew autoremove", "Removing unused dependencies"),
    ]

    success = True
    for cmd, desc in commands:
        print_info(desc)
        if not run_command(cmd, desc):
            success = False

    return success


def cleanup_user_caches():
    """Clean user caches exclude protected ones"""
    cache_dir = Path.home() / "Library" / "Caches"
    cleaned = False
    try:
        for item in cache_dir.iterdir():
            if item.name.startswith(('com.apple', 'Homebrew', 'pip', 'CocoaPods', 'Yarn')):
                # Skip system/specific caches handled elsewhere
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                    cleaned = True
                else:
                    item.unlink()
                    cleaned = True
            except (PermissionError, OSError) as e:
                logging.debug(f"Could not clean {item}: {e}")
                pass
        return True
    except Exception as e:
        logging.error(f"Failed to walk cache dir: {e}")
        return cleaned


def cleanup_user_logs():
    """Clean user logs"""
    logs_dir = Path.home() / "Library" / "Logs"
    try:
        if logs_dir.exists():
            for item in logs_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except (PermissionError, OSError):
                    pass
        return True
    except Exception:
        return False


def cleanup_npm_cache():
    if not shutil.which('npm'):
        return True
    return run_command("npm cache clean --force 2>/dev/null", "npm cache")


def cleanup_pip_cache():
    if not shutil.which('pip3'):
        return True
    return run_command("pip3 cache purge 2>/dev/null", "pip cache")


def cleanup_gem_cache():
    if not shutil.which('gem'):
        return True
    return run_command("gem cleanup 2>/dev/null", "gem cleanup")


def cleanup_trash():
    trash_dir = Path.home() / ".Trash"
    try:
        # On macOS, .Trash permission issues are common.
        for item in trash_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception:
                pass
        return True
    except Exception as e:
        logging.error(f"Trash cleanup error: {e}")
        return False


def cleanup_xcode_derived_data():
    derived_data = Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData"
    if derived_data.exists():
        try:
            shutil.rmtree(derived_data)
            derived_data.mkdir(parents=True)
            return True
        except Exception as e:
            logging.error(f"Xcode DerivedData cleanup error: {e}")
            return False
    return True


def cleanup_xcode_archives():
    archives = Path.home() / "Library" / "Developer" / "Xcode" / "Archives"
    if archives.exists():
        try:
            shutil.rmtree(archives)
            archives.mkdir(parents=True)
            return True
        except Exception as e:
            logging.error(f"Xcode Archives cleanup error: {e}")
            return False
    return True


def cleanup_ios_device_support():
    ios_support = Path.home() / "Library" / "Developer" / "Xcode" / "iOS DeviceSupport"
    if ios_support.exists():
        try:
            for item in ios_support.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                except Exception:
                    pass
            return True
        except Exception as e:
            logging.error(f"iOS DeviceSupport cleanup error: {e}")
            return False
    return True


def cleanup_ios_backups():
    backups_dir = Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"
    if backups_dir.exists():
        try:
            for item in backups_dir.iterdir():
                 if item.is_dir():
                     shutil.rmtree(item)
            return True
        except Exception as e:
            logging.error(f"iOS Backup cleanup error: {e}")
            return False
    return True


def cleanup_simple_cache(path_str):
    path = Path(path_str).expanduser()
    try:
        if path.exists():
            shutil.rmtree(path)
        return True
    except Exception as e:
        logging.error(f"Cleanup failed for {path_str}: {e}")
        return False

def cleanup_docker():
    if not shutil.which('docker'):
        return True
    return run_command(
        "docker system prune -a -f",
        "Docker cleanup"
    )

def cleanup_yarn_cache():
    if not shutil.which('yarn'):
        return True
    return run_command("yarn cache clean", "yarn cache")


def cleanup_pod_cache():
    if not shutil.which('pod'):
        return True
    return run_command("pod cache clean --all", "CocoaPods cache")


def cleanup_vscode_cache():
    paths = [
        Path.home() / "Library" / "Application Support" / "Code" / "CachedData",
        Path.home() / "Library" / "Application Support" / "Code" / "Cache"
    ]
    success = True
    for p in paths:
        if p.exists():
            try:
                shutil.rmtree(p)
            except Exception as e:
                logging.error(f"VS Code cleanup error for {p}: {e}")
                success = False
    return success

# --- Size Functions ---

def get_homebrew_cache_size():
    if not shutil.which('brew'):
        return 0
    # Try getting path from brew
    path = get_path_via_command(['brew', '--cache'])
    if path:
        return get_dir_size(path)
    # Fallback
    cache_path = Path.home() / "Library" / "Caches" / "Homebrew"
    return get_dir_size(str(cache_path))


def get_user_cache_size():
    cache_path = Path.home() / "Library" / "Caches"
    return get_dir_size(str(cache_path))


def get_user_logs_size():
    logs_path = Path.home() / "Library" / "Logs"
    return get_dir_size(str(logs_path))


def get_trash_size():
    trash_path = Path.home() / ".Trash"
    return get_dir_size(str(trash_path))


def get_xcode_size():
    xcode_path = Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData"
    return get_dir_size(str(xcode_path))


def get_xcode_archives_size():
    archives_path = Path.home() / "Library" / "Developer" / "Xcode" / "Archives"
    return get_dir_size(str(archives_path))


def get_ios_device_support_size():
    ios_support = Path.home() / "Library" / "Developer" / "Xcode" / "iOS DeviceSupport"
    return get_dir_size(str(ios_support))


def get_ios_backups_size():
    backups_dir = Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"
    return get_dir_size(str(backups_dir))


def get_npm_cache_size():
    if not shutil.which('npm'):
        return 0
    path = get_path_via_command(['npm', 'config', 'get', 'cache'])
    if path:
        return get_dir_size(path)
    return 0


def get_pip_cache_size():
    if not shutil.which('pip3'):
        return 0
    path = get_path_via_command(['pip3', 'cache', 'dir'])
    if path:
        return get_dir_size(path)

    # Fallback default location
    return get_dir_size(str(Path.home() / "Library" / "Caches" / "pip"))


def get_gem_cache_size():
    if not shutil.which('gem'):
        return 0
    path = get_path_via_command(['gem', 'environment', 'gemdir'])
    if path:
        return get_dir_size(os.path.join(path, 'cache'))
    return 0


def get_docker_size():
    if not shutil.which('docker'):
        return 0
    try:
        # Check if daemon is running
        result = subprocess.run(['docker', 'info'], capture_output=True, timeout=5)
        if result.returncode != 0:
            logging.info("Docker daemon not running, skipping size check")
            return 0

        result = subprocess.run(
            ['docker', 'system', 'df', '--format', '{{.Size}}'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            # Output is like: 1.2GB\n500MB...
            logging.info(f"Docker size report: {result.stdout.strip()}")
            return -1 # Mark as complex to display

    except Exception as e:
        logging.error(f"Docker size check failed: {e}")
        pass
    return 0


def get_yarn_cache_size():
    if not shutil.which('yarn'):
        return 0
    path = get_path_via_command(['yarn', 'cache', 'dir'])
    if path:
        return get_dir_size(path)
    return 0


def get_pod_cache_size():
    if not shutil.which('pod'):
        return 0
    pod_cache = Path.home() / "Library" / "Caches" / "CocoaPods"
    return get_dir_size(str(pod_cache))


def get_spotify_cache_size():
    return get_dir_size(str(Path.home() / "Library" / "Caches" / "com.spotify.client"))


def get_slack_cache_size():
    slack_caches = [
        Path.home() / "Library" / "Application Support" / "Slack" / "Cache",
        Path.home() / "Library" / "Application Support" / "Slack" / "Service Worker" / "CacheStorage",
        Path.home() / "Library" / "Containers" / "com.tinyspeck.slackmacgap" / "Data" / "Library" / "Application Support" / "Slack",
    ]
    total_size = 0
    for cache_dir in slack_caches:
        s = get_dir_size(str(cache_dir))
        if s > 0:
            total_size += s
    return total_size


def get_chrome_cache_size():
    return get_dir_size(str(Path.home() / "Library" / "Caches" / "Google" / "Chrome"))

def get_vscode_cache_size():
    paths = [
        Path.home() / "Library" / "Application Support" / "Code" / "CachedData",
        Path.home() / "Library" / "Application Support" / "Code" / "Cache",
        Path.home() / "Library" / "Application Support" / "Code" / "Backups/workspaces" # Be careful with backups
    ]
    # Only cache and cacheddata
    safe_paths = paths[:2]
    total = 0
    for p in safe_paths:
        s = get_dir_size(str(p))
        if s > 0: total += s
    return total


def main():
    """Main cleanup script"""
    print_header("macOS System Cleanup Utility")
    print_info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Log file: {LOG_FILE}")

    # Show current disk usage
    print_header("Current Disk Usage")
    disk_usage = get_disk_usage()
    if disk_usage:
        print(f"  Total:     {disk_usage['total']}")
        print(f"  Used:      {disk_usage['used']} ({disk_usage['percent']})")
        print(f"  Available: {disk_usage['available']}")

    # Define cleanup tasks
    tasks = [
        CleanupTask(
            "Homebrew Cleanup",
            "Clean Homebrew cache, old versions, and unused dependencies",
            get_homebrew_cache_size,
            cleanup_homebrew
        ),
        CleanupTask(
            "User Caches",
            "Clean ~/Library/Caches (general apps)",
            get_user_cache_size,
            cleanup_user_caches
        ),
        CleanupTask(
            "User Logs",
            "Clean ~/Library/Logs",
            get_user_logs_size,
            cleanup_user_logs
        ),
        CleanupTask(
            "NPM Cache",
            "Clean npm package cache",
            get_npm_cache_size,
            cleanup_npm_cache
        ),
        CleanupTask(
            "Pip Cache",
            "Clean Python pip cache",
            get_pip_cache_size,
            cleanup_pip_cache
        ),
        CleanupTask(
            "Yarn Cache",
            "Clean Yarn package cache",
            get_yarn_cache_size,
            cleanup_yarn_cache
        ),
        CleanupTask(
            "Ruby Gems",
            "Clean old Ruby gems",
            get_gem_cache_size,
            cleanup_gem_cache
        ),
        CleanupTask(
            "CocoaPods Cache",
            "Clean CocoaPods cache",
            get_pod_cache_size,
            cleanup_pod_cache
        ),
        CleanupTask(
            "Trash",
            "Empty Trash (~/.Trash)",
            get_trash_size,
            cleanup_trash
        ),
        CleanupTask(
            "Xcode Derived Data",
            "Clean Xcode build artifacts",
            get_xcode_size,
            cleanup_xcode_derived_data
        ),
        CleanupTask(
            "Xcode Archives",
            "Clean Xcode app archives",
            get_xcode_archives_size,
            cleanup_xcode_archives
        ),
        CleanupTask(
            "iOS Device Support",
            "Clean old iOS device support files",
            get_ios_device_support_size,
            cleanup_ios_device_support
        ),
        CleanupTask(
            "iOS Backups",
            "Clean old iOS device backups",
            get_ios_backups_size,
            cleanup_ios_backups
        ),
        CleanupTask(
            "VS Code Cache",
            "Clean VS Code cached data",
            get_vscode_cache_size,
            cleanup_vscode_cache
        ),
        CleanupTask(
            "Spotify Cache",
            "Clean Spotify app cache",
            get_spotify_cache_size,
            lambda: cleanup_simple_cache("~/Library/Caches/com.spotify.client")
        ),
        CleanupTask(
            "Slack Cache",
            "Clean Slack app cache",
            get_slack_cache_size,
            lambda: cleanup_simple_cache("~/Library/Application Support/Slack/Cache")
        ),
        CleanupTask(
            "Chrome Cache",
            "Clean Google Chrome cache",
            get_chrome_cache_size,
            lambda: cleanup_simple_cache("~/Library/Caches/Google/Chrome")
        ),
        CleanupTask(
            "Docker",
            "Clean Docker containers, images, and cache",
            get_docker_size,
            cleanup_docker
        ),
    ]

    # Calculate sizes
    print_header("Analyzing cleanup opportunities...")
    for task in tasks:
        print_info(f"Checking {task.name}...")
        task.calculate_size()

    # Show overview
    print_header("Cleanup Overview")
    total_size = 0
    for task in tasks:
        size_str = format_size(task.size)
        print(f"  {task.name:.<40} {size_str:>15}")
        if task.size > 0:
            total_size += task.size

    print(f"\n  {'Total estimated cleanup':.<40} {format_size(total_size):>15}")

    # Confirm and execute cleanups
    print_header("Cleanup Actions")
    total_cleaned = 0

    for task in tasks:
        size_str = format_size(task.size)

        print(f"\n{Colors.BOLD}{task.name}{Colors.END}")
        print(f"  {task.description}")
        print(f"  Size: {size_str}")

        if task.size == 0:
             print_info(f"Skipping {task.name} (Empty)")
             continue

        if confirm_action(f"Clean {task.name}?"):
            print_info(f"Cleaning {task.name}...")
            if task.execute():
                print_success(f"Successfully cleaned {task.name}")
                if task.size > 0:
                    total_cleaned += task.size
            else:
                print_warning(f"Some errors occurred while cleaning {task.name}")
        else:
            print_info(f"Skipped {task.name}")

    # Final summary
    print_header("Cleanup Summary")
    print_success(f"Total space freed: {format_size(total_cleaned)}")

    # Show final disk usage
    print_header("Final Disk Usage")
    disk_usage = get_disk_usage()
    if disk_usage:
        print(f"  Total:     {disk_usage['total']}")
        print(f"  Used:      {disk_usage['used']} ({disk_usage['percent']})")
        print(f"  Available: {disk_usage['available']}")

    print_info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\n\nCleanup interrupted by user")
        exit(1)
    except Exception as e:
        print_error(f"\n\nUnexpected error: {str(e)}")
        logging.critical(f"Critical error: {e}", exc_info=True)
        exit(1)
