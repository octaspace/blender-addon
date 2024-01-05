import bpy
from bpy.types import Operator
from threading import Thread


class ModalOperator(Operator):
    _running = False

    def __init__(self):
        self._timer = None
        self._progress = 0
        self._progress_name = ''
        self._run_thread: Thread = None

    @classmethod
    def poll(cls, context):
        return not cls._running

    @classmethod
    def _set_running(cls, value: bool):
        cls._running = value

    @classmethod
    def get_running(cls) -> bool:
        return cls._running

    def get_progress(self):
        return self._progress

    def set_progress(self, value: float):
        self._progress = value
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PROPERTIES':
                    area.tag_redraw()

    def set_progress_name(self, value: str):
        self._progress_name = value

    def get_progress_name(self):
        return self._progress_name

    def modal(self, context, event):
        if event.type == 'TIMER':
            if not self.get_running():
                self.finish(context)
                self._run_thread = None
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        pass
        # TODO: add way to cancel

    def finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self._run_thread = None

    def validate_properties(self, context):
        raise Exception("validate_properties not implemented")

    def invoke(self, context, event):
        if self.get_running():
            return {"CANCELLED"}

        try:
            properties = self.validate_properties(context)
        except:
            # TODO: print error?
            return {"CANCELLED"}
        if properties is None:
            return {"CANCELLED"}

        self._set_running(True)
        self._run_thread = Thread(target=self._thread_run, daemon=True, args=[properties])
        self._run_thread.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _thread_run(self, properties):
        self.set_progress_name('')
        self.set_progress(0)
        try:
            self.run(properties)
        except:
            pass  # TODO: log error
        finally:
            self.set_progress_name('')
            self.set_progress(1)
            self._set_running(False)

    def run(self, properties):
        pass  # overwrite this one
