# winmem_decompress.py

This program tries to extract compressed memory pages from page-aligned data.
Every decompressed page is written to the standard output.

Such compressed memory pages can be found in virtual memory of Windows 8.1 & 10 operating systems.

## Input data

The following types of data can be processed:
* page files;
* crash dumps;
* memory dumps (raw).

## Output data

Every decompressed page should be 4096 bytes in length.
If a decompressed page is truncated (smaller than that), null bytes are used as padding.

Since the program utilizes the brute-force approach to decompress memory pages, many false positives are expected.

## Speed

*The program is very slow.*
The following processing times were seen in a test based on [the 2018 Lone Wolf Scenario](https://digitalcorpora.org/corpora/scenarios/2018-lone-wolf-scenario):
* a page file (2944 MiB): 4 minutes;
* a memory dump (17126 MiB): 6 hours.

## License

The program is made available under the terms of the GNU GPL, version 3.
See the 'License' file.
