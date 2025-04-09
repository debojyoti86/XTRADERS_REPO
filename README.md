# XTraders Trading Application

A powerful desktop trading application built with Python, featuring real-time market data, secure WebSocket connections, and an intuitive Streamlit-based user interface.

## Features

- Real-time market data streaming
- Secure WebSocket connections with enhanced SSL configuration
- Intuitive desktop interface built with webview and Streamlit
- Automated trading capabilities
- Advanced port management and process handling
- Comprehensive error handling and logging

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/xtraders.git
cd xtraders/python_version/modules
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the desktop application:
```bash
python desktop_app_v2.py
```

2. The application will automatically:
   - Start the Streamlit server
   - Initialize trading services (if not in standalone mode)
   - Open the desktop window with the trading interface

## Configuration

- Environment variables can be configured in the `.env` file
- Default port configurations can be modified in `port_utils.py`
- SSL/TLS settings can be adjusted in the security configuration methods

## Security Features

- Enhanced SSL/TLS configuration with modern cipher suites
- Secure WebSocket connections with proper certificate verification
- CORS and XSRF protection
- Environment variable management for sensitive data

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with [Streamlit](https://streamlit.io/)
- Uses [pywebview](https://pywebview.flowrl.com/) for desktop integration