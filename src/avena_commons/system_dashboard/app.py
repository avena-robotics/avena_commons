"""
This application is a web-based system dashboard built using the Flask framework. It provides various functionalities to monitor and display system information. Here's a detailed breakdown of its features:

#Key Features
1. User Authentication:
-  

2. Static File Serving:
-  

- System Data Endpoint: The /data route returns system information in JSON format. This includes CPU, memory, disk, and process information. It also provides a status message (OK or Warning) based on resource usage thresholds.

3. Dynamic Content Rendering:

- Home Page: The / route renders the home page with various system metrics like CPU usage, memory usage, disk usage, kernel info, network info, and system uptime.
- Home Page Content: The /content/index route returns dynamic content for the home page, useful for AJAX requests to update the page without a full reload.
- CPU Page: The /cpu route renders a static page with CPU information.
- CPU Page Content: The /content/cpu route returns dynamic content for the CPU page, useful for AJAX updates.

4. Control Loop (Not Used):
- Control Loop 1: The /control_loop_1 route is intended to render control loop data but is currently not used. It initializes a Controller object with a multiprocessing pipe.

#Helper Functions
- get_system_data(): Collects and returns comprehensive system information, including kernel, CPU, memory, disk, network, and uptime data.

#Flask Configuration
- Session Management: Configured to use the filesystem for session storage.
- Secret Key: A random key is generated for session security.

#Running the Application
- The application runs on all available IP addresses (0.0.0.0), making it accessible from any network interface on the host machine.

#Example Usage
- Accessing the Home Page: Navigate to the root URL (/) to view system metrics.
- Fetching System Data: Make an AJAX request to /data to get real-time system information in JSON format.
- Viewing CPU Information: Navigate to /cpu for detailed CPU metrics or click on Cpu module in the dashboard.
- This application is useful for monitoring system performance and resource usage in real-time, providing both static and dynamic content to the user.
"""

from flask import (
    Flask,
    render_template,
    send_from_directory,
    jsonify,
    request,
    redirect,
    session,
)
from flask_session.__init__ import Session

# from waitress import serve
import os, sys
from .system_status import *
# from multiprocessing import Process, Pipe
# from avena_commons.controller import Controller


def get_system_data():
    """
    Collects and returns system information.
    :return: A dictionary containing information about the system: kernel_info, cpu_info, memory_info, disk_info, network_info, uptime.
    """
    return {
        "kernel_info": get_kernel_info(),
        "cpu_info": get_cpu_info(),
        "memory_info": get_memory_info(),
        "disk_info": get_disk_info(),
        "network_info": get_network_info(),
        "uptime": get_system_uptime(),
    }


def run_app():
    # key = os.urandom(24)
    app = Flask(__name__, static_folder="static", template_folder="templates")
    # app.secret_key = key
    # app.config["SESSION_TYPE"] = "filesystem"
    # Session(app)

    @app.route("/data")
    def data():
        """Returns system data in JSON format. Used for AJAX requests.
        :return: A JSON response containing system information. cpu_info, memory_info, disk_info, process_info, msg.
        """
        memory_info = get_memory_info()
        cpu_info = get_cpu_info()
        disk_info = get_disk_info()
        process_info = get_process_info()

        msg = "OK"
        if (
            cpu_info["total_cpu_usage"] > 80
            or memory_info["memory_percentage"] > 80
            or disk_info["/"]["usage_percentage"] > 80
        ):
            msg = "Warning"
        return jsonify(
            cpu_info=cpu_info,
            memory_info=memory_info,
            disk_info=disk_info,
            process_info=process_info,
            msg=msg,
        )

    @app.route("/")
    def index():
        """Renders the home page.
        :return: The home page template with system information. cpu_usage, cpu_total_cores, memory_usage, memory_total, disk_usage, disk_total_space, kernel_info, network_info, uptime.
        """
        data = get_system_data()
        return render_template(
            "index.html",
            cpu_usage=data["cpu_info"]["total_cpu_usage"],
            cpu_total_cores=data["cpu_info"]["total_cores"],
            memory_usage=data["memory_info"]["memory_percentage"],
            memory_total=round(data["memory_info"]["total_memory"], 2),
            disk_usage=data["disk_info"]["/"]["usage_percentage"],
            disk_total_space=round(data["disk_info"]["/"]["total_space"], 2),
            kernel_info=data["kernel_info"],
            network_info=data["network_info"],
            uptime=data["uptime"],
        )

    @app.route("/content/index")
    def index_content():
        """Returns the home page content in HTML format. Dynamic content.
        :return: The home page content template with system information."""

        data = get_system_data()
        return render_template("partials/index_content.html", **data)

    @app.route("/cpu")
    def cpu_info():
        """Renders the CPU static page.
        :return: The CPU page template with cpu_info."""
        
        cpu_info = get_cpu_info()
        return render_template("cpu.html", cpu_info=cpu_info)

    @app.route("/content/cpu")
    def cpu_content():
        """Returns the CPU page content in HTML format. Dynamic content.
        :return: The CPU page content template with cpu_info."""

        cpu_info = get_cpu_info()

        # Zwracanie tylko fragmentu informacji o CPU
        return render_template("partials/cpu_content.html", cpu_info=cpu_info)

    @app.route("/login")
    def login():
        return redirect("/")
    
    # @app.route("/control_loop_1")
    # def control_loop_1():
    #     """Renders the control loop 1 data. Not USED"""
    #     if not session.get("logged_in"):
    #         return redirect("/login")
    #     _pipe_out, _pipe_in = Pipe()
    #     controller = Controller(suffix=1, pipe_in=_pipe_in)

    app.run(host="0.0.0.0", port=5001)
