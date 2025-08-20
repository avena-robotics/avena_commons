# GETTING STARTED
Import everything that is needed for this module to work.
```python
import sys, os
import threading
import traceback

from avena_commons.util.worker import Worker, Connector
from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import MessageLogger, info, debug, warning, error
```

# Create your new Connector
Those are the basic variables that you need to create inside your class.
- core is the core that the worker will be assigned to.
- frequency is the frequency of the worker loop.
- message_logger is the logger that will be used to log messages. If None, than logs are printed to the console.
- overtime_printer is a boolean that decides if the worker will print information about the overtime of the loop.
- lock is a threading lock that is used to lock the pipe and prevent multiple threads from accessing it at the same time.

```python
class TempConnector(Connector):
    def __init__(
        self, core=8, frequency=100.0, message_logger: MessageLogger = None, overtime_printer=True
    ) -> None:
        self.__core = core
        self.__lock = threading.Lock()
        self.__frequency = frequency
        self._message_logger = message_logger
        self._overtime_printer = overtime_printer
        super().__init__(core=self.__core, message_logger=self._message_logger)

        self._state = None

        super()._connect()
```

Next, you are going to initialize the Connector class. You will assign the core, frequency, message_logger, and overtime_printer to the class variables. Then, you will call the super() method to initialize the Connector class.

Connect will start your new class _run() method. This method will start the Worker class in a new process and pass the pipe_in.

Overriding _run method from connector parent class is mandatory. This method is responsible for starting the worker process.

```python
    def _run(self, pipe_in, message_logger) -> None:
        info(f"Starting run_connector()", message_logger=message_logger)
        worker = TempWorker(
            frequency=self.__frequency,
            message_logger=message_logger,
            overtime_printer=self._overtime_printer,
        )
        worker._run(pipe_in)
```

Next step is to create and override parent send_thru_pipe method. This method is used to send data to the worker process.
You do not want to use this method outside of the class, so we will block it.

```python
    def _send_thru_pipe(self):  # -> Any | None:
        try:
            raise NotImplementedError(
                f"Not implemented: {self._send_thru_pipe.__name__}"
            )
        except NotImplementedError as e:
            error(f"Error: {e}", message_logger=self._message_logger)
```

Last step is to create a destructor method. This method is called when the object is deleted. It will send a stop command to the worker process and return True.

```python
    def __del__(self):
        with self.__lock:
            super()._send_thru_pipe(self._pipe_out, ["STOP"])
            return True
```

Outside of mandatory methods, you can create your own methods and properties. In this example, we have created a property state that is read-only. It is used to get the state of the worker process.

Connector has in-built read-only decorator that will block any attempt to change the value of the property.

```python
    # PROPERTIES
    @property
    def state(self) -> bool:
        with self.__lock:
            state = super()._send_thru_pipe(self._pipe_out, ["GET_STATE"])
            self._state = state if state != None else self._state
            return self._state

    @state.setter
    @Connector._read_only_property("state")
    def state(self, *args):
        pass
```

# Create your new Worker
Those are the basic variables that you need to create inside your class.
- frequency is the frequency of the worker loop.
- message_logger is the logger that will be used to log messages. If None, than logs are printed to the console.
- overtime_printer is a boolean that decides if the worker will print information about the overtime of the loop.

```python
class TempWorker(Worker):
    def __init__(
        self,
        frequency=1000.0,
        message_logger: MessageLogger = None,
        overtime_printer=True,
    ) -> None:
        self._message_logger = message_logger
        super().__init__(message_logger=self._message_logger)
        self._pipe_loop_freq = frequency
        self.overtime_printer = overtime_printer
```

Next step is to create and override parent _run method. This method is the main loop of the worker process. It will run until it receives a stop command. It will also receive and send data to the main process.

Every task that you would like to perform is in the worker process. You can create new getters and setters which will be used as a flags to start something or just to get some data.

```python
    def _run(self, pipe_in) -> None:
        try:
            cl = ControlLoop(
                "TempWorker",
                warning_printer=self.overtime_printer,
                period=1 / self._pipe_loop_freq,
                message_logger=self._message_logger,
            )

            self.state = "Worker New state"

            while True:
                cl.loop_begin()
                if pipe_in.poll(1 / self._pipe_loop_freq):  # default is 0.001
                    # info(f"Received data from pipe")
                    data = pipe_in.recv()
                    match data[0]:
                        case "STOP":
                            debug(
                                f"Stopping worker", message_logger=self._message_logger
                            )
                            pipe_in.send(True)
                            break
                        # GETTERS
                        case "GET_STATE":
                            pipe_in.send(self.state)

                        # SETTERS

                        # if unknown message
                        case _:
                            warning(
                                f"Received unknown message: {data}",
                                message_logger=self._message_logger,
                            )
                            pipe_in.send(False)

                if cl.loop_counter % (1.0 / self._pipe_loop_freq * 5) == 0:
                    info(cl, message_logger=self._message_logger)  # loop info

                cl.loop_end()

        except KeyboardInterrupt:
            pass
        except Exception as e:
            warning(f"Exception in worker: {e}", message_logger=self._message_logger)
            traceback.print_exception(e)
        finally:
            debug(f"Exiting TempWorker subprocess", message_logger=self._message_logger)
```

Worker should not be used to perform any heavy calculations. If anything has to wait for something to happen, Worker should start new thread which perform the task.

In this example you can start a camera in new thread because it will take few seconds to initialize.

You can change state of the worker to like: "Getting data from camera" or "Processing data from camera" etc.

```python
def start_camera(self, data) -> None:
    try:
        # do something
        self.state = "Camera ready"
    except Exception as e:
        warning(f"Exception: {e}", message_logger=self._message_logger)
        self.state = "Error while starting camera"

```
```python
    ...
         match data[0]:
            ...
            # GETTERS
            case "GET_STATE":
                pipe_in.send(self.state)
            ...
            # SETTERS
            case "START_CAMERA":
                t1 = threading.Thread(target=self.start_camera, args=(data[1],)) # data[1] is additional args that we can send to thread from connector main class
                t1.start()
                self.state = "Starting Camera"
                pipe_in.send(True)
            ...
```

After creating setter in worker class you should add some method or property in connector which will be used to start the camera.

```python
def start_camera(self, data) -> None:
    with self.__lock:
        return super()._send_thru_pipe(self._pipe_out, ["START_CAMERA", data])
```

# Example of usage:

Now after creating all the methods and properties you can use your new connector in your main code.

```python
if __name__ == "__main__":
    from multiprocessing import Process, Pipe
    import time

    message_logger = None
    connector = TempConnector(core=5, frequency=1000.0, message_logger=message_logger, overtime_printer=False)
    flag = True
    try:
        while True:
            print(connector.state)
            if flag:
                connector.start_camera("data")
                flag = False
            time.sleep(1)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        warning(f"Exception: {e}", message_logger=message_logger)
    finally:
        del connector
        debug(f"Exiting TempConnector", message_logger=message_logger)
```