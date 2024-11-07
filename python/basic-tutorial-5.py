#!/usr/bin/env python3
import sys
import gi
import logging

gi.require_version("Gst", "1.0")
gi.require_version('Gtk', '3.0')
gi.require_version("GLib", "2.0")
gi.require_version('GdkX11', '3.0')
gi.require_version('GstVideo', '1.0')

from gi.repository import Gst, Gtk, GLib, GdkX11, GstVideo

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)

class CustomData:
    def __init__(self):
        self.playbin = None
        self.sink_widget = None
        self.slider = None
        self.streams_list = None
        self.slider_update_signal_id = None
        self.state = Gst.State.NULL
        self.duration = Gst.CLOCK_TIME_NONE

# This function is called when the PLAY button is clicked
def play_cb(button, data):
    data.playbin.set_state(Gst.State.PLAYING)

# This function is called when the PAUSE button is clicked
def pause_cb(button, data):
    data.playbin.set_state(Gst.State.PAUSED)

# This function is called when the STOP button is clicked
def stop_cb(button, data):
    data.playbin.set_state(Gst.State.READY)

# This function is called when the main window is closed
def delete_event_cb(widget, event, data):
    stop_cb(None, data)
    Gtk.main_quit()

# This function is called when the slider changes its position. We perform a seek to the
# new position here.
def slider_cb(range, data):
    value = data.slider.get_value()
    data.playbin.seek_simple(Gst.Format.TIME,
                             Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                             value * Gst.SECOND)

# This creates all the GTK+ widgets that compose our application, and registers the callbacks
def create_ui(data):
    main_window = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
    main_window.connect("delete-event", delete_event_cb, data)

    play_button = Gtk.Button.new_from_stock(Gtk.STOCK_MEDIA_PLAY)
    play_button.connect("clicked", play_cb, data)

    pause_button = Gtk.Button.new_from_stock(Gtk.STOCK_MEDIA_PAUSE)
    pause_button.connect("clicked", pause_cb, data)

    stop_button = Gtk.Button.new_from_stock(Gtk.STOCK_MEDIA_STOP)
    stop_button.connect("clicked", stop_cb, data)

    data.slider = Gtk.HScale.new_with_range(0, 100, 1)
    data.slider.set_draw_value(False)
    data.slider_update_signal_id = data.slider.connect("value-changed", slider_cb, data)

    data.streams_list = Gtk.TextView.new()
    data.streams_list.set_editable(False)

    controls = Gtk.HBox.new(False, 0)
    controls.pack_start(play_button, False, False, 2)
    controls.pack_start(pause_button, False, False, 2)
    controls.pack_start(stop_button, False, False, 2)
    controls.pack_start(data.slider, True, True, 0)

    main_hbox = Gtk.HBox.new(False, 0)
    main_hbox.pack_start(data.sink_widget, True, True, 0)
    main_hbox.pack_start(data.streams_list, False, False, 2)

    main_box = Gtk.VBox.new(False, 0)
    main_box.pack_start(main_hbox, True, True, 0)
    main_box.pack_start(controls, False, False, 0)

    main_window.add(main_box)
    main_window.set_default_size(640, 480)
    main_window.show_all()

# This function is called periodically to refresh the GUI
def refresh_ui(data):
    current = -1

    # We do not want to update anything unless we are in the PAUSED or PLAYING states
    if data.state < Gst.State.PAUSED:
        return True

    # If we didn't know it yet, query the stream duration
    if data.duration == Gst.CLOCK_TIME_NONE:
        ret, data.duration = data.playbin.query_duration(Gst.Format.TIME)
        if not ret:
            logger.error("Could not query current duration.")
        else:
            # Set the range of the slider to the clip duration, in SECONDS
            data.slider.set_range(0, data.duration / Gst.SECOND)

    ret, current = data.playbin.query_position(Gst.Format.TIME)
    if ret:
        # Block the "value-changed" signal, so the slider_cb function is not called
        # (which would trigger a seek the user has not requested)
        data.slider.handler_block(data.slider_update_signal_id)

        # Set the position of the slider to the current pipeline positoin, in SECONDS
        data.slider.set_value(current / Gst.SECOND)

        # Re-enable the signal
        data.slider.handler_unblock(data.slider_update_signal_id)

    return True

# This function is called when new metadata is discovered in the stream
def tags_cb(playbin, stream, data):
    # We are possibly in a GStreamer working thread, so we notify the main
    # thread of this event through a message in the bus
    data.playbin.post_message(
        Gst.Message.new_application(
            data.playbin, Gst.Structure.new_empty("tags-changed")))

# This function is called when an error message is posted on the bus
def error_cb(bus, msg, data):
    err, debug_info = msg.parse_error()
    logger.error("Error received from element {s}: {s}".format(
        msg.src.get_name(),
        err.message))
    logger.error("Debugging information: {debug_info if debug_info else 'none'}")

    data.playbin.set_state(Gst.State.READY)

# This function is called when an End-Of-Stream message is posted on the bus.
# We just set the pipeline to READY (which stops playback)
def eos_cb(bus, msg, data):
    logger.info("End-Of-Stream reached.")
    data.playbin.set_state(Gst.State.READY)

# This function is called when the pipeline changes states. We use it to
# keep track of the current state.
def state_changed_cb(bus, msg, data):
    old_stated, new_state, pending_state = msg.parse_state_changed()
    if msg.src == data.playbin:
        data.state = new_state

        logger.info("State changed from {0} to {1}".format(
            Gst.Element.state_get_name(old_stated),
            Gst.Element.state_get_name(new_state)))

        if old_stated == Gst.State.READY and new_state == Gst.State.PAUSED:
            # For extra responsiveness, we refresh the GUI as soon as we reach the PAUSED state
            refresh_ui()

# Extract metadata from all the streams and write it to the text widget in the GUI
def analyze_streams(data):
    # Clean current contents of the widget
    buffer = data.streams_list.get_buffer()
    buffer.set_text("")

    # Read some properties
    n_video = data.playbin.get_property("n-video")
    n_audio = data.playbin.get_property("n-audio")
    n_text = data.playbin.get_property("n-text")

    for i in range(n_video):
        # Retrieve the stream's video tags
        tags = data.playbin.emit("get-video-tags", i)
        if tags:
            buffer.insert_at_cursor("video stream {0}\n".format(i))
            ret, str = tags.get_string(Gst.TAG_VIDEO_CODEC)
            buffer.insert_at_cursor("  codec: {0}\n".format(str or "unknown"))

    for i in range(n_audio):
        # Retrieve the stream's audio tags
        tags = data.playbin.emit("get-audio-tags", i)
        if tags:
            buffer.insert_at_cursor("\naudio stream {0}\n".format(i))
            ret, str = tags.get_string(Gst.TAG_AUDIO_CODEC)
            if ret:
                buffer.insert_at_cursor("  codec: {0}\n".format(str or "unknown"))

            ret, str = tags.get_string(Gst.TAG_LANGUAGE_CODE)
            if ret:
                buffer.insert_at_cursor("  language: {0}\n".format(str or "unknown"))

            ret, str = tags.get_string(Gst.TAG_BITRATE)
            if ret:
                buffer.insert_at_cursor("  bitrate: {0}\n".format(str or "unknown"))

    for i in range(n_text):
        # Retrieve the stream's subtitle tags
        tags = data.playbin.emit("get-text-tags", i)
        if tags:
            buffer.insert_at_cursor("\nsubtitle stream {0}\n".format(i))
            ret, str = tags.get_string(Gst.TAG_LANGUAGE_CODE)
            if ret:
                buffer.insert_at_cursor("  language: {0}\n".format(str or "unknown"))

# This function is called when an "application" message is posted on the bus.
# Here we retrieve the message posted by the tags_cb callback
def application_cb(bus, msg, data):
    if msg.get_structure().get_name() == "tags-changed":
        # If the message is the "tags-changed" (only one we are currently issuing), update
        # the stream info GUI
        analyze_streams()

def tutorial_main():
    # Initialize GTK
    Gtk.init(sys.argv)

    # Initialize GStreamer
    Gst.init(sys.argv)

    # Initialize our data structure
    data = CustomData()

    # Create the elements
    data.playbin = Gst.ElementFactory.make("playbin", "playbin")

    videosink = Gst.ElementFactory.make("glsinkbin", "glsinkbin")
    gtkglsink = Gst.ElementFactory.make("gtkglsink", "gtkglsink")

    # Here we create the GTK Sink element which will provide us with a GTK widget where
    # GStreamer will render the video at and we can add to our UI.
    # Try to create the OpenGL version of the video sink, and fallback if that fails
    if videosink and gtkglsink:
        logger.info("Successfully created GTK GL Sink")

        videosink.set_property("sink", gtkglsink)

        # The gtkglsink creates the gtk widget for us. This is accessible through a property.
        # So we get it and use it later to add it to our gui.
        data.sink_widget = gtkglsink.get_property("widget")
    else:
        logger.error("Could not create gtkglsink, falling back to gtksink.")

        videosink = Gst.ElementFactory.make("gtksink", "gtksink")
        data.sink_widget = videosink.get_property("widget")

    if not data.playbin or not videosink:
        logger.error("Not all elements could be created.")
        sys.exit(1)

    # Set the URI to play
    data.playbin.set_property("uri", "https://gstreamer.freedesktop.org/data/media/sintel_trailer-480p.webm")

    # Set the video-sink. The playbin assumes ownership of videosink, because
    # that's still a floating reference.
    data.playbin.set_property("video-sink", videosink)

    # Connect to interesting signals in playbin
    data.playbin.connect("video-tags-changed", tags_cb, data)
    data.playbin.connect("audio-tags-changed", tags_cb, data)
    data.playbin.connect("text-tags-changed", tags_cb, data)

    # Create the GUI
    create_ui(data)

    # Instruct the bus to emit signals for each received message, and connect to the interesting signals
    bus = data.playbin.get_bus()
    bus.add_signal_watch()
    bus.connect("message::error", error_cb, data)
    bus.connect("message::eos", eos_cb, data)
    bus.connect("message::state-changed", state_changed_cb, data)
    bus.connect("message::application", application_cb, data)

    # Start playing
    ret = data.playbin.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        logger.error("Unable to set the pipeline to the playing state.")
        sys.exit(1)

    # Register a function that GLib will call every second
    GLib.timeout_add_seconds(1, refresh_ui)

    # Start the GTK main loop. We will not regain control until gtk_main_quit is called.
    Gtk.main()

    # Free resourcesFree resources
    data.playbin.set_state(Gst.State.NULL)

if __name__ == "__main__":
    tutorial_main()

