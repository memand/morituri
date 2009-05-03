# -*- Mode: Python; test-case-name: morituri.test.test_image_cue -*-
# vi:si:et:sw=4:sts=4:ts=4

# Morituri - for those about to RIP

# Copyright (C) 2009 Thomas Vander Stichele

# This file is part of morituri.
# 
# morituri is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# morituri is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with morituri.  If not, see <http://www.gnu.org/licenses/>.

"""
Reading .cue files

See http://digitalx.org/cuesheetsyntax.php
"""

import os
import re

from morituri.common import common

_REM_RE = re.compile("^REM\s(\w+)\s(.*)$")
_PERFORMER_RE = re.compile("^PERFORMER\s(.*)$")
_TITLE_RE = re.compile("^TITLE\s(.*)$")

_FILE_RE = re.compile(r"""
    ^FILE                 # FILE
    \s+"(?P<name>.*)"     # 'file name' in quotes
    \s+(?P<format>\w+)$   # format (WAVE/MP3/AIFF/...)
""", re.VERBOSE)

_TRACK_RE = re.compile(r"""
    ^\s+TRACK            # TRACK
    \s+(?P<track>\d\d)   # two-digit track number
    \s+(?P<mode>.+)$    # mode (AUDIO, MODEx/2xxx, ...)
""", re.VERBOSE)

_INDEX_RE = re.compile(r"""
    ^\s+INDEX   # INDEX
    \s+(\d\d)   # two-digit index number
    \s+(\d\d)   # minutes
    :(\d\d)     # seconds
    :(\d\d)$    # frames
""", re.VERBOSE)


class Cue:
    def __init__(self, path):
        self._path = path
        self._rems = {}
        self._messages = []
        self.tracks = []

    def parse(self):
        state = 'HEADER'
        currentFile = None
        currentTrack = None

        handle = open(self._path, 'r')

        for number, line in enumerate(handle.readlines()):
            line = line.rstrip()

            m = _REM_RE.search(line)
            if m:
                tag = m.expand('\\1')
                value = m.expand('\\2')
                if state != 'HEADER':
                    self.message(number, 'REM %s outside of header' % tag)
                else:
                    self._rems[tag] = value
                continue

            # look for FILE lines
            m = _FILE_RE.search(line)
            if m:
                filePath = m.group('name')
                fileFormat = m.group('format')
                currentFile = File(filePath, fileFormat)

            # look for TRACK lines
            m = _TRACK_RE.search(line)
            if m:
                if not currentFile:
                    self.message(number, 'TRACK without preceding FILE')
                    continue

                state = 'TRACK'

                trackNumber = int(m.group('track'))
                trackMode = m.group('mode')

                currentTrack = Track(trackNumber)
                self.tracks.append(currentTrack)
                continue

            # look for INDEX lines
            m = _INDEX_RE.search(line)
            if m:
                if not currentTrack:
                    self.message(number, 'INDEX without preceding TRACK')
                    print 'ouch'
                    continue

                indexNumber = int(m.expand('\\1'))
                minutes = int(m.expand('\\2'))
                seconds = int(m.expand('\\3'))
                frames = int(m.expand('\\4'))

                frameOffset = frames + seconds * 75 + minutes * 75 * 60
                currentTrack.index(indexNumber, frameOffset, currentFile)
                # print 'index %d, offset %d of track %r' % (indexNumber, frameOffset, currentTrack)
                continue

    def dump(self):
        """
        Dump our internal representation to a .cue file content.
        """
        lines = []
        currentFile = None

        for i, track in enumerate(self.tracks):
            indexes = track._indexes.keys()
            indexes.sort()
            index, file = track._indexes[indexes[0]]
            if file != currentFile:
                lines.append('FILE "%s" WAVE' % file.path)
                currentFile = file
            lines.append("  TRACK %02d %s" % (i + 1, 'AUDIO'))
            for index in indexes:
                (offset, file) = track._indexes[index]
                if file != currentFile:
                    lines.append('FILE "%s" WAVE' % file.path)
                lines.append(
                    "    INDEX %02d %s" % (index, common.framesToMSF(offset)))

        lines.append("")
        return "\n".join(lines) 

    def message(self, number, message):
        """
        Add a message about a given line in the cue file.

        @param number: line number, counting from 0.
        """
        self._messages.append((number + 1, message))

    def getTrackLength(self, track):
        # returns track length in frames, or -1 if can't be determined and
        # complete file should be assumed
        # FIXME: this assumes a track can only be in one file; is this true ?
        i = self.tracks.index(track)
        if i == len(self.tracks) - 1:
            # last track, so no length known
            return -1

        thisIndex = track._indexes[1] # FIXME: could be more
        nextIndex = self.tracks[i + 1]._indexes[1] # FIXME: could be 0

        if thisIndex[1] == nextIndex[1]: # same file
            return nextIndex[0] - thisIndex[0]

        # FIXME: more logic
        return -1

    def getRealPath(self, path):
        """
        Translate the .cue's FILE to an existing path.
        """
        if os.path.exists(path):
            return path

        # .cue FILE statements have Windows-style path separators, so convert
        tpath = os.path.join(*path.split('\\'))
        candidatePaths = []

        # if the path is relative:
        # - check relatively to the cue file
        # - check only the filename part relative to the cue file
        if tpath == os.path.abspath(tpath):
            candidatePaths.append(tPath)
        else:
            candidatePaths.append(os.path.join(
                os.path.dirname(self._path), tpath))
            candidatePaths.append(os.path.join(
                os.path.dirname(self._path), os.path.basename(tpath)))

        for candidate in candidatePaths:
            noext, _ = os.path.splitext(candidate)
            for ext in ['wav', 'flac']:
                cpath = '%s.%s' % (noext, ext)
                if os.path.exists(cpath):
                    return cpath

        raise KeyError, "Cannot find file for %s" % path


class File:
    """
    I represent a FILE line in a cue file.
    """
    def __init__(self, path, format):
        self.path = path
        self.format = format

    def __repr__(self):
        return '<File "%s" of format %s>' % (self.path, self.format)


# FIXME: add type ? separate AUDIO from others
class Track:
    """
    I represent a track in a cue file.
    I have index points.
    Each index point is linked to an audio file.

    @ivar number: track number
    @type number: int
    """

    def __init__(self, number):
        if number < 1 or number > 99:
            raise IndexError, "Track number must be from 1 to 99"

        self.number = number
        self._indexes = {} # index number -> (sector, File)

        self.title = None
        self.performer = None

    def __repr__(self):
        return '<Track %02d with %d indexes>' % (self.number,
            len(self._indexes.keys()))

    def index(self, number, sector, file):
        """
        Add the given index to the current track.

        @type file: L{File}
        """
        if number in self._indexes.keys():
            raise KeyError, "index %d already in track %d" % (
                number, self.number)
        if number < 0 or number > 99:
            raise IndexError, "Index number must be from 0 to 99"

        self._indexes[number] = (sector, file)

    def getIndex(self, number):
        """
        @rtype: tuple of (int, File)
        """
        return self._indexes[number]
