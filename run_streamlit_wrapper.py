"""
Wrapper to ensure the local project directory is added to sys.path before
importing the Streamlit app module. Use this when Streamlit can't find a local module.

Run:
  streamlit run run_streamlit_wrapper.py

This will print some diagnostic info to the terminal where you ran Streamlit.
"""
import os
import sys

BASE_DIR = os.path.dirname(__file__) or os.getcwd()
# Ensure the script directory is first on sys.path
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Diagnostic helper — prints to the Streamlit server console (not browser)
print("Base dir added to sys.path:", BASE_DIR)
print("sys.path[0:5]:", sys.path[:5])
print("Files in base dir:", os.listdir(BASE_DIR))

# Now import and run the Streamlit app module (it will execute top-level Streamlit code)
try:
    import swift_alliance_streamlit  # noqa: E402
except Exception as e:
    # Print full exception trace to terminal for easier debugging
    import traceback
    traceback.print_exc()
    raise