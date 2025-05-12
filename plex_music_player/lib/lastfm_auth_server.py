import http.server
import socketserver
import urllib.parse
import webbrowser
import socket
from threading import Thread
from typing import Callable, Optional
from ..lib.logger import Logger

logger = Logger()

def is_port_available(port: int) -> bool:
    """Check if the port is available."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False

class LastFMAuthHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, callback: Callable[[str], None], **kwargs):
        self.callback = callback
        super().__init__(*args, **kwargs)

    def do_GET(self):
        logger.debug(f"Received GET request: {self.path}")
        if self.path.startswith("/callback"):
            # Parse the token from the URL
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            if "token" in params:
                token = params["token"][0]
                logger.debug(f"Received token: {token}")
                
                # Send success response with auto-close
                logger.debug("Preparing success response")
                self.send_response(200)
                logger.debug("Sending Content-type header")
                self.send_header("Content-type", "text/html")
                logger.debug("Ending headers")
                self.end_headers()
                response_html = b"""
                    <html>
                        <head>
                            <title>Last.fm Authorization Success</title>
                            <style>
                                body {
                                    background-color: #1e1e1e;
                                    color: white;
                                    font-family: Arial, sans-serif;
                                    text-align: center;
                                    padding-top: 50px;
                                }
                                .success-icon {
                                    color: #4CAF50;
                                    font-size: 48px;
                                    margin-bottom: 20px;
                                }
                            </style>
                        </head>
                        <body>
                            <div class="success-icon">&check;</div>
                            <h1>Success!</h1>
                            <p>Last.fm authorization completed successfully.</p>
                            <p>You can close this window and return to the application.</p>
                            <script>
                                // Close window after 2 seconds
                                setTimeout(function() {
                                    window.close();
                                }, 2000);
                            </script>
                        </body>
                    </html>
                """
                try:
                    logger.debug("Writing response to browser")
                    self.wfile.write(response_html)
                    logger.debug("Success response sent to browser")
                    
                    # Call callback after sending response
                    logger.debug("Calling callback function with token")
                    self.callback(token)
                    logger.debug("Callback function completed successfully")
                except Exception as e:
                    logger.error(f"Error in callback function: {e}")
            else:
                logger.error("No token received in callback")
                # Send error response
                logger.debug("Preparing error response")
                self.send_response(400)
                logger.debug("Sending Content-type header")
                self.send_header("Content-type", "text/html")
                logger.debug("Ending headers")
                self.end_headers()
                response_html = b"""
                    <html>
                        <head>
                            <title>Last.fm Authorization Error</title>
                            <style>
                                body {
                                    background-color: #1e1e1e;
                                    color: white;
                                    font-family: Arial, sans-serif;
                                    text-align: center;
                                    padding-top: 50px;
                                }
                                .error-icon {
                                    color: #f44336;
                                    font-size: 48px;
                                    margin-bottom: 20px;
                                }
                            </style>
                        </head>
                        <body>
                            <div class="error-icon">&times;</div>
                            <h1>Error</h1>
                            <p>No token received. Please try again.</p>
                            <script>
                                // Close window after 3 seconds
                                setTimeout(function() {
                                    window.close();
                                }, 3000);
                            </script>
                        </body>
                    </html>
                """
                try:
                    logger.debug("Writing error response to browser")
                    self.wfile.write(response_html)
                    logger.debug("Error response sent to browser")
                except Exception as e:
                    logger.error(f"Error sending response to browser: {e}")

class LastFMAuthServer:
    def __init__(self, callback: Callable[[str], None], port: int = 8080):
        self.port = port
        self.callback = callback
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[Thread] = None

    def start(self):
        try:
            # Try alternative ports if the main port is not available
            alternative_ports = [8080, 8081, 8082, 8083, 8084]
            port_used = None
            
            for port in alternative_ports:
                logger.debug(f"Checking if port {port} is available")
                if is_port_available(port):
                    port_used = port
                    break
                    
            if port_used is None:
                logger.error("No available ports found")
                raise RuntimeError("No available ports found. Please close some applications and try again.")

            logger.debug(f"Starting Last.fm auth server on port {port_used}")
            handler = lambda *args, **kwargs: LastFMAuthHandler(*args, callback=self.callback, **kwargs)
            self.server = socketserver.TCPServer(("", port_used), handler)
            self.thread = Thread(target=self.server.serve_forever)
            self.thread.daemon = True
            self.thread.start()
            logger.debug("Last.fm auth server started successfully")
            
            # Update the port
            self.port = port_used
        except Exception as e:
            logger.error(f"Failed to start Last.fm auth server: {e}")
            raise

    def stop(self):
        if self.server:
            logger.debug("Stopping Last.fm auth server")
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.thread = None
            logger.debug("Last.fm auth server stopped")

def open_auth_url(api_key: str, port: int = 8080) -> None:
    """Open Last.fm authentication URL in the default browser."""
    auth_url = f"https://www.last.fm/api/auth/?api_key={api_key}&cb=http://localhost:{port}/callback"
    logger.debug(f"Opening auth URL: {auth_url}")
    webbrowser.open(auth_url) 