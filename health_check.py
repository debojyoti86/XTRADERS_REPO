import streamlit as st
from streamlit.web.server.server import Server
from streamlit.runtime.scriptrunner import get_script_run_ctx

def health_check():
    """Health check endpoint to verify server status"""
    try:
        # Get current server instance
        ctx = get_script_run_ctx()
        if ctx is None:
            st.error('No server context available')
            return False
            
        # Verify server state
        server = Server.get_current()
        if server is None:
            st.error('No server instance available')
            return False
            
        # Check if server is running and responsive
        if not server.started:
            st.error('Server not fully started')
            return False
            
        return True
    except Exception as e:
        st.error(f'Health check failed: {str(e)}')
        return False

# Add health check endpoint
if __name__ == '__main__':
    if st.experimental_get_query_params().get('healthz'):
        is_healthy = health_check()
        if is_healthy:
            st.success('Server is healthy')
            st.stop()
        else:
            st.error('Server is unhealthy')
            st.stop()