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
        self.playbin = None
        self.playing = False
        self.terminate = False
        self.seek_enabled = False
        self.seek_done = False
        self.duration = Gst.CLOCK_TIME_NONE

def tutorial_main():
    data = CustomData()
    ret = None

    # Initialize GStreamer
    Gst.init(sys.argv[1:])

    # Create the elements
    data.playbin = Gst.ElementFactory.make("playbin", "playbin")

    if not data.playbin:
        logger.error("Not all elements could be created.")
        sys.exit(1)

    # Set the URI to play
    data.playbin.set_property("uri", "http://docs.gstreamer.com/media/sintel_trailer-480p.webm")

    # Start playing
    ret = data.playbin.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        logger.error("Unable to set the pipeline to the playing state.")
        sys.exit(1)

    # Listen to the bus
    bus = data.playbin.get_bus()

    while not data.terminate:
        msg = bus.timed_pop_filtered(100 * Gst.MSECOND,
                                     Gst.MessageType.STATE_CHANGED | Gst.MessageType.ERROR | Gst.MessageType.EOS | Gst.MessageType.DURATION_CHANGED)

        # Parse message
        if msg:
            handle_message(data, msg)
        else:
            # We got no message, this means the timeout expired
            if data.playing:
                # Query the current position of the stream
                ret, current = data.playbin.query_position(Gst.Format.TIME)
                if not current:
                    logger.error("Could not query current position.")

                # If we didn't know it yet, query the stream duration
                if data.duration == Gst.CLOCK_TIME_NONE:
                    data.duration = data.playbin.query_duration(Gst.Format.TIME)
                    if not data.duration:
                        logger.error("Could not query current duration.")

                # print current position and total duration
                logger.info("Position {0} / {1}".format(current, data.duration))

                # If seeking is enabled, we have not done it yet, and the time is right, seek
                if data.seek_enabled and not data.seek_done and current > 10 * Gst.SECOND:
                    data.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 30 * Gst.SECOND)
                    data.seek_done = True

            if data.terminate:
                break

    # Free resources
    data.pipeline.set_state(Gst.State.NULL)

def handle_message(data, msg):
    logger.info("handle_message start")

    if msg.type == Gst.MessageType.ERROR:
        err = msg.parse_error()
        logger.error("ERROR:", msg.src.get_name(), ":", err)
        data.terminate = True
    elif msg.type == Gst.MessageType.EOS:
        logger.info("End-Of-Stream reached.")
        data.terminate = True
    elif msg.type == Gst.MessageType.DURATION_CHANGED:
        data.duration = Gst.CLOCK_TIME_NONE
    elif msg.type == Gst.MessageType.STATE_CHANGED:
        old_state, new_state, pending_state = msg.parse_state_changed()

        logger.info("Pipeline state changed from '{0:s}' to '{1:s}'"
                    .format(Gst.Element.state_get_name(old_state), Gst.Element.state_get_name(new_state)))

        if msg.src == data.playbin:
            # Remember whether we are in the PLAYING state or not
            data.playing = (new_state == Gst.State.PLAYING)

            if data.playing:
                # We just moved to PLAYING. Check if seeking is possible
                query = Gst.Query.new_seeking(Gst.Format.TIME)
                if data.playbin.query(query):
                    fmt, data.seek_enabled, start, end = query.parse_seeking()

                    if data.seek_enabled:
                        logger.info("Seeking is ENABLED (from {0} to {1})".format(start, end))
                    else:
                        logger.info("Seeking is DISABLED for this stream")
                else:
                    logger.error("Seeking query failed.")
    else:
        # We should not reach here
        logger.error("Unexpected message received.")

if __name__ == "__main__":
    tutorial_main()

