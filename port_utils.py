import socket
import psutil
import time
from typing import Optional, List

def is_port_in_use(port: int) -> bool:
    """Check if a port is currently in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except socket.error:
            return True

def find_process_using_port(port: int) -> Optional[psutil.Process]:
    """Find the process that is using the specified port."""
    for proc in psutil.process_iter(['pid', 'name', 'connections']):
        try:
            connections = proc.connections()
            for conn in connections:
                if conn.laddr.port == port:
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def find_available_port(start_port: int, end_port: int = 65535) -> Optional[int]:
    """Find an available port in the specified range."""
    for port in range(start_port, end_port + 1):
        if not is_port_in_use(port):
            return port
    return None

def terminate_process_on_port(port: int, timeout: int = 5) -> bool:
    """Attempt to terminate the process using the specified port."""
    process = find_process_using_port(port)
    if not process:
        return True

    try:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except psutil.TimeoutExpired:
            process.kill()
        return True
    except psutil.NoSuchProcess:
        return True
    except Exception as e:
        print(f"Error terminating process: {e}")
        return False

def ensure_port_available(port: int, max_attempts: int = 3) -> bool:
    """Ensure a port is available by attempting to terminate any process using it."""
    for attempt in range(max_attempts):
        if not is_port_in_use(port):
            return True
            
        if terminate_process_on_port(port):
            time.sleep(0.5)  # Wait for port to be fully released
            if not is_port_in_use(port):
                return True
                
        if attempt < max_attempts - 1:
            time.sleep(1)  # Wait before next attempt
            
    return False