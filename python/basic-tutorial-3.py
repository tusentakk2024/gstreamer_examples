#!/usr/bin/env python3
import sys
import gi
import logging

gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gst, GLib, GObject

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)

class CustomData:
    def __init__(self):
        self.pipeline = None
        self.source = None
        self.convert = None
        self.resample = None
        self.sink = None

def tutorial_main():
    data = CustomData()

    # Initialize GStreamer
    Gst.init(sys.argv[1:])

    # Create the elements
    data.source = Gst.ElementFactory.make("uridecodebin", "source")
    data.convert = Gst.ElementFactory.make("audioconvert", "convert")
    data.resample = Gst.ElementFactory.make("audioresample", "resample")
    data.sink = Gst.ElementFactory.make("autoaudiosink", "sink")

    # Create the empty pipeline
    data.pipeline = Gst.Pipeline.new("test-pipeline")

    if not data.pipeline or not data.source or not data.convert or not data.resample or not data.sink:
        logger.error("Not all elements could be created.")
        sys.exit(1)

    # Build the pipeline
    data.pipeline.add(data.source)
    data.pipeline.add(data.convert)
    data.pipeline.add(data.resample)
    data.pipeline.add(data.sink)
    if not data.convert.link(data.sink):
        logger.error("Elements could not be linked.")
        sys.exit(1)

    # Set the URI to play
    data.source.set_property("uri", "http://docs.gstreamer.com/media/sintel_trailer-480p.webm")

    # Connect to the pad-added signal
    data.source.connect("pad-added", pad_added_handler, data)

    # Start playing
    ret = data.pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        logger.error("Unable to set the pipeline to the playing state.")
        sys.exit(1)

    # Listen to the bus
    bus = data.pipeline.get_bus()
    terminate = False

    while True:
        msg = bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE,
                                     Gst.MessageType.STATE_CHANGED | Gst.MessageType.ERROR | Gst.MessageType.EOS)

        # Parse message
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, debug_info = msg.parse_error()
                logger.error("Error received from element {s}: {s}".format(
                    msg.src.get_name(),
                    err.message))
                logger.error("Debugging information: {debug_info if debug_info else 'none'}")
                terminate = True
            elif msg.type == Gst.MessageType.EOS:
                logger.info("End-Of-Stream reached.")
                terminate = True
            elif msg.type == Gst.MessageType.STATE_CHANGED:
                # We are only interested in state-changed messages from the pipeline
                if msg.src == data.pipeline:
                    old_state, new_state, pending_state = msg.parse_state_changed()
                    logger.info("Pipeline state changed from {0:s} to {1:s}".format(
                        Gst.Element.state_get_name(old_state),
                        Gst.Element.state_get_name(new_state)))
            else:
                # This should not happen as we only asked for ERRORs and EOS
                logger.error("Unexpected message received.")
                terminate = True

        if terminate:
            break

    data.pipeline.set_state(Gst.State.NULL)

# This function will be called by the pad-added signal
def pad_added_handler(src, new_pad, data):
    sink_pad = data.convert.get_static_pad("sink")

    logger.info("Received new pad '{0:s}' from '{1:s}'".format(
        new_pad.get_name(),
        src.get_name()))

    # If our converter is already linked, we have nothing to do here
    if (sink_pad.is_linked()):
        logger.error("We are already linked. Ignoring.")
        return

    # Check the new pad's type
    new_pad_caps = new_pad.get_current_caps()
    new_pad_struct = new_pad_caps.get_structure(0)
    new_pad_type = new_pad_struct.get_name()

    if not new_pad_type.startswith("audio/x-raw"):
        logger.error("It has type {0:s} which is not raw audio. Ignoring.".format(new_pad_type))
        return

    # attempt the link
    ret = new_pad.link(sink_pad)
    if not ret == Gst.PadLinkReturn.OK:
        logger.info("Type is {0:s} but link failed".format(new_pad_type))
    else:
        logger.info("Link succeeded (type {0:s})".format(new_pad_type))

if __name__ == "__main__":
    tutorial_main()

