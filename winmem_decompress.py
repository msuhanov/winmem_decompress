#!/usr/bin/env python3

# (c) Maxim Suhanov

import os
import sys
import time
import io
import struct
import multiprocessing

PROGRAM_VERSION = '20180925'
PARALLEL_TASKS = 4 # The number of decompression tasks to run in parallel.

PAGE_SIZE = 4096
COMPRESSED_DATA_CHUNK_SIZE = 16

DECOMPRESSED_DATA_SIZE_MIN = 1024 # Ignore decompressed data chunks which are smaller than this value.

def LZ77DecompressBuffer(Buffer):
	"""Decompress data from Buffer using the plain LZ77 algorithm, return the decompressed data."""

	def is_valid_write_request(offset):
		return offset < 2*1024*1024*1024 # Reject obviously invalid write requests.

	OutputObject = io.BytesIO()

	BufferedFlags = 0
	BufferedFlagCount = 0
	InputPosition = 0
	OutputPosition = 0
	LastLengthHalfByte = 0

	while True:
		if BufferedFlagCount == 0:
			BufferedFlags = Buffer[InputPosition : InputPosition + 4]

			if len(BufferedFlags) != 4:
				# Bogus data.
				break

			BufferedFlags, = struct.unpack('<L', BufferedFlags)

			InputPosition += 4
			BufferedFlagCount = 32

		BufferedFlagCount -= 1
		if BufferedFlags & (1 << BufferedFlagCount) == 0:
			try:
				OneByte = Buffer[InputPosition]
			except IndexError:
				# Bogus data.
				break

			if type(OneByte) is not int:
				OneByte = ord(OneByte)

			OneByte = bytearray([OneByte])

			if is_valid_write_request(OutputPosition):
				OutputObject.seek(OutputPosition)
				OutputObject.write(OneByte)
			else:
				# Bogus data.
				break

			InputPosition += 1
			OutputPosition += 1
		else:
			if InputPosition == len(Buffer):
				# We are done.
				OutputBuffer = OutputObject.getvalue()
				OutputObject.close()

				return OutputBuffer

			MatchBytes = Buffer[InputPosition : InputPosition + 2]
			if len(MatchBytes) != 2:
				# Bogus data.
				break

			MatchBytes, = struct.unpack('<H', MatchBytes)

			InputPosition += 2
			MatchLength = MatchBytes % 8
			MatchOffset = (MatchBytes // 8) + 1
			if MatchLength == 7:
				if LastLengthHalfByte == 0:
					try:
						MatchLength = Buffer[InputPosition]
					except IndexError:
						# Bogus data.
						break

					if type(MatchLength) is not int:
						MatchLength = ord(MatchLength)

					MatchLength = MatchLength % 16
					LastLengthHalfByte = InputPosition
					InputPosition += 1
				else:
					try:
						MatchLength = Buffer[LastLengthHalfByte]
					except IndexError:
						# Bogus data.
						break

					if type(MatchLength) is not int:
						MatchLength = ord(MatchLength)

					MatchLength = MatchLength // 16
					LastLengthHalfByte = 0

				if MatchLength == 15:
					try:
						MatchLength = Buffer[InputPosition]
					except IndexError:
						# Bogus data.
						break

					if type(MatchLength) is not int:
						MatchLength = ord(MatchLength)

					InputPosition += 1
					if MatchLength == 255:
						MatchLength = Buffer[InputPosition : InputPosition + 2]
						if len(MatchLength) != 2:
							# Bogus data.
							break

						MatchLength, = struct.unpack('<H', MatchLength)
						InputPosition += 2
						if MatchLength < 15 + 7:
							# Bogus data.
							break

						MatchLength -= (15 + 7)

					MatchLength += 15

				MatchLength += 7

			MatchLength += 3

			bogus_data = False
			for i in range(0, MatchLength):
				if OutputPosition - MatchOffset < 0:
					# Bogus data.
					bogus_data = True
					break

				OutputObject.seek(OutputPosition - MatchOffset)
				OneByte = OutputObject.read(1)

				if len(OneByte) != 1:
					# Bogus data.
					bogus_data = True
					break

				if is_valid_write_request(OutputPosition):
					OutputObject.seek(OutputPosition)
					OutputObject.write(OneByte)
				else:
					# Bogus data.
					bogus_data = True
					break

				OutputPosition += 1

			if bogus_data:
				break

	# We are done (but data is bogus).
	OutputBuffer = OutputObject.getvalue()
	OutputObject.close()

	return OutputBuffer

def ScanBuffer(Buffer):
	"""Scan Buffer for compressed data chunks, yield every decompressed data chunk."""

	global pool

	null_bytes_12 = b'\x00' * 12

	compressed_data_to_process = []

	pos = 0
	while pos < len(Buffer):
		compressed_data = Buffer[pos : pos + PAGE_SIZE]

		if not compressed_data.startswith(null_bytes_12): # Check if data starts with many null bytes.
			compressed_data_to_process.append(compressed_data)

		pos += COMPRESSED_DATA_CHUNK_SIZE # Compressed memory pages are stored in chunks.

	for decompressed_data in pool.imap_unordered(LZ77DecompressBuffer, compressed_data_to_process, chunksize = 8):
		if len(decompressed_data) >= DECOMPRESSED_DATA_SIZE_MIN:
			if len(decompressed_data) > PAGE_SIZE:
				# Remove garbage after the decompressed page.
				decompressed_data = decompressed_data[ : PAGE_SIZE]
			elif len(decompressed_data) < PAGE_SIZE:
				# Add padding bytes to keep the output aligned.
				padding_length = PAGE_SIZE - len(decompressed_data)
				decompressed_data += b'\x00' * padding_length

			yield decompressed_data

def ScanFile(FilePath):
	"""Scan a given file for compressed data chunks, yield every decompressed data chunk."""

	read_chunk_size = 32 * PAGE_SIZE

	with open(FilePath, 'rb') as file_obj:
		file_obj.seek(0, 2)
		file_size = file_obj.tell()

		file_pos = 0
		while file_pos < file_size:
			file_obj.seek(file_pos)
			buf = file_obj.read(read_chunk_size)

			for data in ScanBuffer(buf):
				yield data

			if len(buf) != read_chunk_size:
				# End of a file or a read error.
				break

			file_pos += read_chunk_size

def PrintUsage():
	"""Print the usage information."""

	print('winmem_decompress, version: {}'.format(PROGRAM_VERSION), file = sys.stderr)
	print('', file = sys.stderr)
	print('This program tries to extract compressed memory pages from page-aligned data.', file = sys.stderr)
	print('Every decompressed page is written to the standard output.', file = sys.stderr)
	print('', file = sys.stderr)
	print('Usage: {} <input file>'.format(sys.argv[0]), file = sys.stderr)

if __name__ == '__main__':
	if len(sys.argv) != 2:
		PrintUsage()
		sys.exit(1)

	file_path = sys.argv[1]
	if not os.path.isfile(file_path):
		print('File doesn\'t exist: {}'.format(file_path), file = sys.stderr)
		sys.exit(1)

	pool = multiprocessing.Pool(processes = PARALLEL_TASKS)
	time_start = round(time.time())

	for data in ScanFile(file_path):
		sys.stdout.buffer.write(data)

	pool.close()
	pool.join()
	time_end = round(time.time())

	print('Processing done in {} seconds.'.format(time_end - time_start), file = sys.stderr)
