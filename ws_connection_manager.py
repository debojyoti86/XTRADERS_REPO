import ssl
import time
import socket
import threading
import websocket
import requests
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

class WebSocketConnectionManager:
    def __init__(self, base_url: str, dev_url: str, heartbeat_interval: int = 30,
                 max_reconnect_attempts: int = 10, reconnect_delay: int = 10,
                 connection_timeout: int = 30):
        self.base_url = base_url
        self.dev_url = dev_url
        self.active_url = base_url
        self.heartbeat_interval = heartbeat_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.connection_timeout = connection_timeout
        self.connections: Dict[str, Dict[str, Any]] = {}
        self._ws_lock = threading.Lock()
        self._stop_heartbeat: Dict[str, threading.Event] = {}
        self._last_heartbeat: Dict[str, float] = {}
        self._ssl_context = None
        self._init_ssl_context()

    def _init_ssl_context(self):
        """Initialize SSL context with enhanced security defaults and modern cipher suites"""
        try:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.verify_mode = ssl.CERT_REQUIRED  # Enable certificate verification
            self._ssl_context.check_hostname = True  # Enable hostname verification
            self._ssl_context.load_default_certs()
            
            # Use strong cipher suites with forward secrecy and modern algorithms
            self._ssl_context.set_ciphers(
                'ECDHE-ECDSA-AES256-GCM-SHA384:'
                'ECDHE-RSA-AES256-GCM-SHA384:'
                'ECDHE-ECDSA-CHACHA20-POLY1305:'
                'ECDHE-RSA-CHACHA20-POLY1305:'
                'ECDHE-ECDSA-AES128-GCM-SHA256:'
                'ECDHE-RSA-AES128-GCM-SHA256'
            )
            
            # Disable older protocols and enable security options
            self._ssl_context.options |= (
                ssl.OP_NO_TLSv1 | 
                ssl.OP_NO_TLSv1_1 | 
                ssl.OP_NO_COMPRESSION |  # Prevent CRIME attack
                ssl.OP_CIPHER_SERVER_PREFERENCE |  # Use server's cipher preferences
                ssl.OP_SINGLE_DH_USE |  # Ensure perfect forward secrecy
                ssl.OP_SINGLE_ECDH_USE  # Ensure perfect forward secrecy for ECDH
            )
            
            self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2  # Enforce minimum TLS 1.2
            
            # Set session parameters
            self._ssl_context.options |= ssl.OP_NO_TICKET  # Disable session tickets
            self._ssl_context.options |= ssl.OP_NO_RENEGOTIATION  # Disable renegotiation
            
            print("✓ SSL context initialized successfully with certificate verification")
            
        except ssl.SSLError as ssl_err:
            print(f"SSL Error: {ssl_err}")
            raise
        except Exception as e:
            print(f"Error initializing SSL context: {str(e)}")
            raise


    def get_ssl_context(self, hostname: str) -> ssl.SSLContext:
        """Create a secure SSL context with proper certificate verification"""
        context = ssl.create_default_context()
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_default_certs()
        context.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256')
        return context

    def verify_server_availability(self) -> bool:
        """Verify WebSocket server availability with enhanced health checks and fallback support"""
        for url in [self.base_url, self.dev_url]:
            try:
                health_check_url = f"{url.replace('wss://', 'https://')}/healthz"
                response = requests.get(
                    health_check_url,
                    timeout=self.connection_timeout/3,
                    verify=True,
                    headers={
                        'User-Agent': 'XTraders/1.0',
                        'Connection': 'keep-alive'
                    },
                    cert=self._ssl_context.get_ca_certs() if self._ssl_context else None
                )
                
                if response.status_code == 200:
                    self.active_url = url
                    return True
                    
            except requests.exceptions.SSLError as ssl_err:
                print(f"SSL verification failed for {url}: {ssl_err}")
                self._init_ssl_context()  # Reinitialize SSL context
                
            except requests.exceptions.RequestException as e:
                print(f"Server health check failed for {url}: {e}")
                
        return False

        # Try development server as fallback
        try:
            if self.base_url != self.dev_url:
                health_check_url = f"{self.dev_url.replace('ws://', 'http://')}/healthz"
                response = requests.get(
                    health_check_url,
                    timeout=self.connection_timeout/3,
                    verify=False
                )
                if response.status_code == 200:
                    self.active_url = self.dev_url
                    return True
        except requests.exceptions.RequestException as e:
            print(f"Development server health check failed: {e}")

        return False

    def initialize_connection(self, exchange_name: str, callbacks: Dict[str, callable], bind_address: Optional[str] = None) -> bool:
        """Initialize WebSocket connection with comprehensive error handling, state management and binding support"""
        with self._ws_lock:
            try:
                # Verify server availability first
                if not self.verify_server_availability():
                    raise ConnectionError("Server not available")
                
                # Initialize or verify SSL context
                if self.active_url.startswith('wss'):
                    try:
                        ssl_context = self._ssl_context or self.get_ssl_context(self.active_url.replace('wss://', '').split('/')[0])
                        if not ssl_context:
                            raise Exception("SSL context initialization failed")
                    except Exception as ssl_err:
                        print(f"SSL context error: {ssl_err}")
                        self._init_ssl_context()  # Reinitialize SSL context
                        ssl_context = self._ssl_context
                        if not ssl_context:
                            raise Exception("Failed to initialize SSL context after retry")
                
                current_time = time.time()
                
                # Initialize or update connection state with enhanced tracking
                if exchange_name not in self.connections:
                    self.connections[exchange_name] = {
                        'connected': False,
                        'last_heartbeat': current_time,
                        'last_activity': current_time,
                        'reconnect_attempts': 0,
                        'consecutive_failures': 0,
                        'recovery_mode': False,
                        'last_error': None,
                        'connection_start_time': None,
                        'last_successful_connection': None,
                        'connection_quality': 1.0,
                        'connection_state': 'initializing',
                        'last_state_change': current_time,
                        'error_count': 0,
                        'successful_messages': 0
                    }

                state = self.connections[exchange_name]
                current_time = time.time()

                # Handle recovery mode
                if state['recovery_mode']:
                    if current_time - state.get('last_error_time', 0) < 60:
                        return False
                    state['recovery_mode'] = False
                    state['consecutive_failures'] = 0

                # Configure WebSocket with enhanced security and binding
                ws_url = f"{self.active_url}/ws/{exchange_name}"
                ssl_options = None
                if self.active_url.startswith('wss'):
                    ssl_options = {
                        'context': ssl_context,
                        'cert_reqs': ssl.CERT_REQUIRED,
                        'check_hostname': True,
                        'ssl_version': ssl.PROTOCOL_TLS,
                        'ciphers': 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384'
                    }

                # Configure socket binding if address is provided
                socket_opts = []
                if bind_address:
                    try:
                        host, port = bind_address.split(':') if ':' in bind_address else (bind_address, None)
                        socket_opts.append((socket.SOL_SOCKET, socket.SO_REUSEADDR, 1))
                        if port:
                            socket_opts.append((socket.SOL_SOCKET, socket.SO_REUSEPORT, 1))
                    except Exception as bind_err:
                        print(f"Warning: Invalid bind address format: {bind_err}")
                        bind_address = None

                # Create WebSocket with binding support
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_message=callbacks.get('on_message'),
                    on_error=callbacks.get('on_error'),
                    on_close=callbacks.get('on_close'),
                    on_open=callbacks.get('on_open'),
                    on_ping=callbacks.get('on_ping'),
                    on_pong=callbacks.get('on_pong'),
                    header={'User-Agent': 'XTraders/1.0'}
                )

                # Apply socket options and binding
                if socket_opts:
                    ws.sock_opt = socket_opts
                if bind_address:
                    ws.bind_addr = bind_address

                # Update connection state
                state['connection_state'] = 'connecting'
                state['last_state_change'] = current_time

                # Configure WebSocket monitoring and health checks
                def ws_monitor():
                    try:
                        ws.run_forever(
                            ping_interval=max(self.heartbeat_interval/3, 10),
                            ping_timeout=max(self.heartbeat_interval/6, 5),
                            ping_payload='ping',
                            sslopt={
                                'context': ssl_context,
                                'cert_reqs': ssl.CERT_REQUIRED,
                                'check_hostname': True,
                                'ssl_version': ssl.PROTOCOL_TLS,
                                'ciphers': 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384'
                            } if ssl_context else None
                        )
                    except Exception as e:
                        state['last_error'] = str(e)
                        state['connection_state'] = 'error'
                        state['last_state_change'] = time.time()
                        state['error_count'] += 1
                        print(f"WebSocket error in {exchange_name}: {str(e)}")

                # Start WebSocket monitoring thread
                ws_thread = threading.Thread(
                    target=ws_monitor,
                    daemon=True,
                    name=f"ws-{exchange_name}"
                )
                ws_thread.start()

                # Enhanced connection verification with state tracking
                timeout = time.time() + self.connection_timeout
                while time.time() < timeout:
                    if state['connection_state'] == 'error':
                        raise Exception(f"Connection failed: {state['last_error']}")
                    if state['connected']:
                        state['connection_state'] = 'connected'
                        state['last_state_change'] = time.time()
                        break
                    time.sleep(0.2)

                if not state['connected']:
                    state['connection_state'] = 'timeout'
                    state['last_state_change'] = time.time()
                    raise Exception("Connection timeout")

                # Start heartbeat monitoring
                self._start_heartbeat_monitor(exchange_name)

                state['last_successful_connection'] = current_time
                state['connection_start_time'] = current_time
                state['recovery_mode'] = False
                state['consecutive_failures'] = 0
                state['reconnect_attempts'] = 0

                return True

            except Exception as e:
                error_msg = f"WebSocket initialization failed: {str(e)}"
                print(error_msg)
                state['last_error'] = error_msg
                state['last_error_time'] = time.time()
                state['consecutive_failures'] += 1
                state['reconnect_attempts'] += 1

                if state['consecutive_failures'] >= self.max_reconnect_attempts:
                    state['recovery_mode'] = True

                return False

    def handle_connection_error(self, exchange_name: str, error: Any) -> None:
        """Handle WebSocket errors with enhanced recovery strategies and state management"""
        if exchange_name not in self.connections:
            return

        state = self.connections[exchange_name]
        current_time = time.time()
        state['connected'] = False
        state['last_error'] = str(error)
        state['last_error_time'] = current_time
        state['consecutive_failures'] = state.get('consecutive_failures', 0) + 1

        # Handle SSL/TLS specific errors
        error_msg = str(error).lower()
        if 'ssl' in error_msg or 'certificate' in error_msg:
            print(f"SSL/TLS error detected for {exchange_name}: {error_msg}")
            try:
                # Attempt to refresh SSL context
                if hasattr(self, 'ssl_context') and self.ssl_context:
                    self.ssl_context = self._create_ssl_context()
                    print(f"Refreshed SSL context for {exchange_name}")
            except Exception as ssl_error:
                print(f"Failed to refresh SSL context: {str(ssl_error)}")

        # Calculate backoff time with jitter for better distribution
        jitter = random.uniform(0.8, 1.2)
        base_backoff = min(
            self.reconnect_delay * (2 ** (state['consecutive_failures'] - 1)),
            300  # Cap maximum backoff at 5 minutes
        )
        backoff_time = base_backoff * jitter
        
        # Update state with next reconnect time
        state['next_reconnect_time'] = current_time + backoff_time

        # Handle different failure scenarios
        if state['consecutive_failures'] <= self.max_reconnect_attempts:
            print(f"Scheduling reconnection for {exchange_name} in {backoff_time:.2f} seconds")
            threading.Timer(
                backoff_time,
                lambda: self.try_reconnect(exchange_name)
            ).start()
        else:
            state['recovery_mode'] = True
            print(f"Connection to {exchange_name} entering recovery mode due to excessive failures")
            # Try fallback URL if available
            if self.active_url == self.base_url and self.dev_url:
                print(f"Switching to fallback URL for {exchange_name}")
                self.active_url = self.dev_url
                state['consecutive_failures'] = 0  # Reset counter for new endpoint
                # Immediate attempt with new URL
                threading.Timer(1, lambda: self.try_reconnect(exchange_name)).start()

        # Update connection quality metrics
        if state.get('connection_start_time'):
            uptime = current_time - state['connection_start_time']
            error_rate = state['consecutive_failures'] / max(uptime, 1)
            state['connection_quality'] = max(0.1, min(1.0, 1.0 - error_rate))
            
            # Log detailed connection statistics
            print(f"{exchange_name} connection stats: Quality={state['connection_quality']:.2f}, "
                  f"Uptime={uptime:.1f}s, Failures={state['consecutive_failures']}")


    def _attempt_reconnect(self, exchange_name: str) -> None:
        """Attempt to reconnect with proper state management and error handling"""
        if exchange_name not in self.connections:
            return

        state = self.connections[exchange_name]
        if state['connected'] or state.get('reconnecting', False):
            return

        with self._ws_lock:
            try:
                state['reconnecting'] = True
                print(f"Attempting to reconnect to {exchange_name}...")

                # Verify server availability before attempting reconnection
                if not self.verify_server_availability():
                    raise Exception("Server unavailable")

                # Get the stored callbacks for this connection
                callbacks = state.get('callbacks', {})
                if not callbacks:
                    raise Exception("No callbacks available for reconnection")

                # Attempt to initialize new connection
                if self.initialize_connection(exchange_name, callbacks):
                    print(f"Successfully reconnected to {exchange_name}")
                    state['last_successful_connection'] = time.time()
                    state['consecutive_failures'] = 0
                    state['reconnect_attempts'] = 0
                    state['recovery_mode'] = False
                else:
                    raise Exception("Failed to initialize connection")

            except Exception as e:
                print(f"Reconnection attempt failed for {exchange_name}: {str(e)}")
                state['last_error'] = str(e)
                state['last_error_time'] = time.time()
                
                # Schedule next reconnection attempt if needed
                if state['consecutive_failures'] < self.max_reconnect_attempts:
                    backoff_time = min(30, self.reconnect_delay * (2 ** state['consecutive_failures']))
                    threading.Timer(backoff_time, self._attempt_reconnect, args=[exchange_name]).start()
                else:
                    print(f"Max reconnection attempts reached for {exchange_name}")
                    state['recovery_mode'] = True

            finally:
                state['reconnecting'] = False
            error_rate = state['consecutive_failures'] / connection_duration
            state['connection_quality'] = max(0.0, 1.0 - (error_rate * 10))

        # Enhanced error analysis and recovery
        if isinstance(error, (websocket.WebSocketConnectionClosedException, ConnectionResetError)):
            state['reconnect_attempts'] = 0  # Reset for connection errors
            self._check_network_connectivity()
            # Implement exponential backoff for reconnection
            delay = min(self.reconnect_delay * (2 ** state['consecutive_failures']), 300)
            time.sleep(delay)
        elif isinstance(error, ssl.SSLError):
            # Reinitialize SSL context with enhanced security
            self._init_ssl_context()
            # Verify SSL configuration
            try:
                ssl_context = self.get_ssl_context(self.active_url.replace('wss://', '').split('/')[0])
                if ssl_context:
                    print(f"SSL context reinitialized for {exchange_name}")
            except Exception as e:
                print(f"SSL context reinitialization failed: {e}")
            try:
                self._init_ssl_context()
                self._ssl_context.verify_mode = ssl.CERT_REQUIRED
                self._ssl_context.check_hostname = True
            except Exception as ssl_err:
                print(f"SSL configuration error: {ssl_err}")
                self._notify_connection_failure(exchange_name, f"SSL Error: {ssl_err}")
                return

        # Progressive recovery mode with adaptive delays
        if state['consecutive_failures'] >= 3:
            if not state.get('recovery_mode'):
                state['recovery_mode'] = True
                state['recovery_start_time'] = time.time()
                print(f"Entering recovery mode for {exchange_name}")
            
            # Extended cooling period for persistent failures
            cooling_period = min(30 * (2 ** (state['consecutive_failures'] - 3)), 300)
            time.sleep(cooling_period)
            
            # Reset failure count after cooling
            if time.time() - state.get('recovery_start_time', 0) > 600:  # 10 minutes
                state['consecutive_failures'] = 0
                state['recovery_mode'] = False

        # Attempt reconnection with exponential backoff
        if state['reconnect_attempts'] < self.max_reconnect_attempts:
            state['reconnect_attempts'] += 1
            delay = min(self.reconnect_delay * (2 ** (state['reconnect_attempts'] - 1)), 60)
            print(f"Reconnecting to {exchange_name} in {delay:.2f} seconds (attempt {state['reconnect_attempts']}/{self.max_reconnect_attempts})")
            time.sleep(delay)
            
            # Verify server availability before reconnecting
            if self.verify_server_availability():
                self._attempt_reconnect(exchange_name)
            else:
                print(f"Server unavailable for {exchange_name}, will retry later")
        else:
            self._notify_connection_failure(exchange_name, str(error))
            
    def _check_network_connectivity(self) -> bool:
        """Check network connectivity to major internet services"""
        test_urls = ['https://8.8.8.8', 'https://1.1.1.1']
        for url in test_urls:
            try:
                requests.get(url, timeout=5)
                return True
            except requests.exceptions.RequestException:
                continue
        return False

    def _attempt_reconnect(self, exchange_name: str) -> None:
        """Attempt to reconnect with proper initialization"""
        try:
            # Reset connection state
            if exchange_name in self.connections:
                state = self.connections[exchange_name]
                state['connected'] = False
                state['connecting'] = True
                
                # Initialize new connection with updated SSL context
                ws = websocket.WebSocketApp(
                    self.active_url,
                    on_open=lambda ws: self._on_open(ws, exchange_name),
                    on_close=lambda ws: self._on_close(ws, exchange_name),
                    on_error=lambda ws, err: self.handle_connection_error(exchange_name, err),
                    sslopt={
                        "context": self._ssl_context,
                        "check_hostname": True
                    }
                )
                
                # Start connection in background thread
                threading.Thread(target=ws.run_forever).start()
        except Exception as e:
            print(f"Reconnection attempt failed for {exchange_name}: {e}")
            self.handle_connection_error(exchange_name, e)

    def _start_heartbeat_monitoring(self, exchange_name: str) -> None:
        """Start heartbeat monitoring for a connection"""
        if exchange_name in self._stop_heartbeat:
            self._stop_heartbeat[exchange_name].set()
        
        self._stop_heartbeat[exchange_name] = threading.Event()
        self._last_heartbeat[exchange_name] = time.time()
        
        def monitor_heartbeat():
            while not self._stop_heartbeat[exchange_name].is_set():
                current_time = time.time()
                last_heartbeat = self._last_heartbeat.get(exchange_name, 0)
                
                if current_time - last_heartbeat > self.heartbeat_interval * 2:
                    print(f"No heartbeat received from {exchange_name} for {self.heartbeat_interval * 2} seconds")
                    if exchange_name in self.connections:
                        state = self.connections[exchange_name]
                        if state.get('connected', False):
                            print(f"Connection appears stale for {exchange_name}, initiating reconnection")
                            self.handle_connection_error(exchange_name, "Heartbeat timeout")
                
                time.sleep(self.heartbeat_interval / 2)
        
        threading.Thread(target=monitor_heartbeat, daemon=True).start()
    
    def update_heartbeat(self, exchange_name: str) -> None:
        """Update the last heartbeat timestamp for a connection"""
        self._last_heartbeat[exchange_name] = time.time()
    
    def _notify_connection_failure(self, exchange_name: str, error: str) -> None:
        """Notify about persistent connection issues with detailed diagnostics"""
        state = self.connections.get(exchange_name, {})
        
        print("\nConnection Failure Diagnostic Report:")
        print(f"Exchange: {exchange_name}")
        print(f"Error: {error}")
        print(f"Last Successful Connection: {datetime.fromtimestamp(state.get('last_successful_connection', 0)).strftime('%Y-%m-%d %H:%M:%S') if state.get('last_successful_connection') else 'Never'}")
        print(f"Consecutive Failures: {state.get('consecutive_failures', 0)}")
        print(f"Total Reconnection Attempts: {state.get('reconnect_attempts', 0)}")
        print(f"Connection Quality: {state.get('connection_quality', 0)}")
        print(f"Recovery Mode: {state.get('recovery_mode', False)}")
        print(f"Connection URL: {self.active_url}")

        # Stop heartbeat monitoring
        if exchange_name in self._stop_heartbeat:
            self._stop_heartbeat[exchange_name].set()
            
        # Cleanup connection state
        if exchange_name in self.connections:
            self.connections[exchange_name]['connected'] = False
            self.connections[exchange_name]['last_error'] = error

        # Attempt fallback if using production URL
        if self.active_url == self.base_url:
            print("Attempting fallback to development server...")
            self.active_url = self.dev_url
            state['reconnect_attempts'] = 0
        else:
            print("\nRecommended Actions:")
            print("1. Check network connectivity")
            print("2. Verify WebSocket server status")
            print("3. Check SSL certificate validity")
            print("4. Review firewall settings")
            print("5. Contact system administrator if issues persist\n")
