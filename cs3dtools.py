#!/usr/bin/env python
#
#    Copyright (C) 2021  Ludburgh Miyajima (MechanoPixel)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import os
import argparse
from struct import unpack
from wand import image

def readInt32(fp): # read LE int32
  return int.from_bytes(fp.read(4), byteorder='little', signed=True)

def toChar(byte):
  if byte >= b'\x20' and byte <= b'\x7E':
    return byte.decode('ascii')
  return "_"

def convertTexture(segmentData):
  width  = unpack('<L', segmentData[0x24:0x27+1])[0]
  height = unpack('<L', segmentData[0x28:0x2B+1])[0]
  size   = int(((width * height) * 16) / 8)
  print(f" - Detected Size - ")
  print(f"{width}x{height} ({size})")
  headerTemplate = bytearray(b"\x00"*128)
  headerTemplate[0:12] = b"\x44\x44\x53\x20\x7C\x00\x00\x00\x07\x10\x08\x00"
  headerTemplate[12:12+4] = width.to_bytes(4, byteorder='little')
  headerTemplate[16:16+4] = height.to_bytes(4, byteorder='little')
  headerTemplate[22:22+1] = b"\x08"
  headerTemplate[76:76+1] = b"\x20"
  headerTemplate[80:80+1] = b"\x40"
  headerTemplate[88:88+1] = b"\x10"
  headerTemplate[93:93+1] = b"\xF8"
  headerTemplate[96:96+2] = b"\xE0\x07"
  headerTemplate[100:100+1] = b"\x1F"
  headerTemplate[109:109+1] = b"\x10"
  ddsData = bytearray(segmentData)
  ddsData[0:56] = headerTemplate
  return(bytes(ddsData[0:0x80+size]))

def findOffsets(segmentData):
  fOffsetBytes = segmentData[0x130:0x134]
  fOffset = unpack('<I', fOffsetBytes)[0]
  
  fCountBytes = segmentData[0x128:0x12C]
  fCount = unpack('<I', fCountBytes)[0]
  
  vOffsetBytes = segmentData[0x134:0x138]
  vOffset = unpack('<I', vOffsetBytes)[0]
  
  vCountBytes = segmentData[0x124:0x128]
  vCount = unpack('<I', vCountBytes)[0]
  vLength = len(segmentData)
  
  vtPadding = 32
  vPadding = 28
  if segmentData[vOffset+52:vOffset+52+4] != b"\xFF"*4:
    vtPadding = 28
    vPadding = 24
  
  return(fOffset, fCount, vOffset, vPadding, vCount, vtPadding)

def convertMesh(segmentData):
  fOffset, fCount, vOffset, vPadding, vCount, vtPadding = findOffsets(segmentData)
  
  print(f" - Detected Offsets - ")
  print(f"f:  {hex(fOffset)} ({fCount})")
  print(f"v:  {hex(vOffset)} ({vCount}+{vPadding})")
  print(f"vt: {hex(vOffset+28)} ({vCount}+{vtPadding})")
  
  fSectionOut = ""
  # Faces
  i = 0
  while i < int(fCount/3):
    currentOffset = fOffset+(6*i)
    currentSegment = segmentData[currentOffset:currentOffset+6]
    v1, v2, v3 = unpack('<HHH', currentSegment)
    #print(f"{i}/{int(fCount/3)}: {currentSegment.hex()}")
    fSectionOut += f"f  {v1+1}/{v1+1} {v2+1}/{v2+1} {v3+1}/{v3+1}\n"
    i += 1

  brokenFile = False
  vSectionOut = ""
  # Vertices
  i = 0
  currentOffset = vOffset
  while i < vCount:
    currentSegment = segmentData[currentOffset:currentOffset+12]
    if len(currentSegment) < 12:
      break
    #print(f"v{i}: {currentSegment.hex()}")
    x, y, z = unpack('<fff', currentSegment)
    #vSectionOut += f"v  {format(x, f'.{acc}f')} {format(y, f'.{acc}f')} {format(z, f'.{acc}f')}\n"
    if x!=x or y!=y or z!=z:
      brokenFile = True
    vSectionOut += f"v  {x} {y} {z}\n"
    currentOffset += 12+vPadding
    i += 1
  
  vtSectionOut = ""
  # UVs
  i = 0
  currentOffset = vOffset+28
  while i < vCount: # vtCount and vCount are the same
    currentSegment = segmentData[currentOffset:currentOffset+8]
    if len(currentSegment) < 8:
      break
    #print(f"vt{i}: {currentSegment.hex()}")
    u, v = unpack('<ff', currentSegment)
    if u!=u or v!=v:
      brokenFile = True
    #vtSectionOut += f"vt  {format(u, f'.{acc}f')} {format(v, f'.{acc}f')}\n"
    vtSectionOut += f"vt  {u} {v}\n"
    currentOffset += 8+vtPadding
    i += 1
    
  if brokenFile:
    print("Warning: Errors detected, file may be broken!")
  return(f"{vSectionOut}{vtSectionOut}{fSectionOut}")

def convertMaterial(segmentData):
  pass

def checkType(segmentData):
  if segmentData[0x30:0x37+1] == b'\x00\x00\x00\x00\x38\x00\x00\x00':
    return( 'TXTR' )
  if segmentData[0x12c:0x12f+1] == b'\x50\x01\x00\x00':
    return( 'MESH' )
  if segmentData[0x300:0x307+1] == b'\x00\x00\x80\x3F\x00\x00\x00\x00':
    return( 'SKIN' )
  if segmentData[0x100:0x107+1] == b'\xFF\xFF\x7F\x7F\xFF\xFF\x7F\xFF':
    return( 'POSE' )
  if segmentData[0x154:0x15B+1] == b'\x80\x01\x00\x00\x00\x00\x00\x00':
    return( 'LVLD' )
  if segmentData[0x148:0x14B+1] == b'\x00\x00\x80\x3F':
    return( 'NODE' )
  if segmentData[0x110:0x11f+1] == b'\x00\x00\x80\x3F\x00\x00\x80\x3F\x00\x00\x80\x3F\x00\x00\x80\x3F':
    return( 'MATR' )
  if segmentData[0x8:0xf+1] == b'\x63\x73\x5F\x52\x4F\x4F\x54\x5F':
    return( 'ROOT' )
  return( 'UNKN' )

def readString(fp): # read null terminated string without moving pointer
  previousOffset = fp.tell()
  string = ""
  while (True):
    currentByte = fp.read(1)
    if not currentByte == b"\x00":
      string += toChar(currentByte)
    else:
      break
  fp.seek(previousOffset, 0)
  return string

def extract_n3d(args):
  n3dPathRaw = args.extract[0][1:-1]
  n3dPathNoExtension = "".join(n3dPathRaw.split('.')[0:-1])
  n3dPath = n3dPathNoExtension
  if len(n3dPathNoExtension) < 1:
    n3dPath = n3dPathRaw
  
  with open(n3dPath+'.n3dhdr', 'rb') as hdrFilePointer:
    n3dName = n3dPath.split('/')[-1]
    n3dDirectory = f"processed/{n3dName}"
    segmentsDirectory = f"{n3dDirectory}/segments"
    convertedDirectory = f"{n3dDirectory}/converted"
    if not os.path.exists(n3dDirectory):
      os.makedirs(n3dDirectory)
      os.makedirs(segmentsDirectory)
      os.makedirs(convertedDirectory)
    # Retrieve amount of segments in file (this offset is pretty much constant)
    hdrFilePointer.seek(256, 0)
    totalSegments = readInt32(hdrFilePointer)
    print("There are", totalSegments, "segments in this file.")
    dtaFilePointer = open(n3dPath+'.n3ddta', 'rb')
    for segmentIndex in range(0, totalSegments):
      # Layout: UNKNOWN (4 bytes), Offset (4 bytes), Length (4 bytes)
      hdrFilePointer.seek(4, 1) # skip unknown
      segmentOffset = readInt32(hdrFilePointer) # read offset
      segmentLength = readInt32(hdrFilePointer) # read length

      dtaFilePointer.seek(segmentOffset, 0)
      segmentName = readString(dtaFilePointer)
      segmentData = dtaFilePointer.read(segmentLength)
      segmentType = checkType(segmentData)
      print(f"Writing segment {segmentIndex} [{segmentType}]: {segmentName}")
      
      with open(f'{segmentsDirectory}/{segmentIndex} - {segmentName}.sgmt', 'wb') as sgmtFilePointer:
        sgmtFilePointer.write(segmentData)
        sgmtFilePointer.close()
      if segmentType == 'TXTR':
        ddsData = convertTexture(segmentData)
        if args.convertimages:
          ddsImage = image.Image(blob=ddsData)
          pngImage = ddsImage.clone()
          pngImage.flip()
          pngImage.save(filename=f"{convertedDirectory}/{segmentIndex} - {segmentName}.png")
        else:
          with open(f"{convertedDirectory}/{segmentIndex} - {segmentName}.dds", "wb") as ddsFilePointer:
            ddsFilePointer.write(ddsData)
            ddsFilePointer.close()
          
      if segmentType == 'MESH':
        objData = convertMesh(segmentData)
        with open(f"{convertedDirectory}/{segmentIndex} - {segmentName}.obj", "w") as objFilePointer:
          objFilePointer.write(objData)
          objFilePointer.close()

    hdrFilePointer.close()
    dtaFilePointer.close()
    
def write_n3d(args):
  print("Error: this is not implemented yet, but will be later")

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Toolkit for working with n3dhdr/n3ddta files from Cave Story 3D.")
  parser.add_argument("--extract", type=ascii, metavar="input_filename", nargs=1, help="")
  parser.add_argument("--create", type=ascii, metavar="output_filename", nargs=1, help="")
  parser.add_argument("--convertimages", action='store_true', help="Flips textures vertically and outputs them as PNGs.")
  args = parser.parse_args()
  mode = "a"
  if args.extract:
    extract_n3d(args)
  elif args.create:
    write_n3d(args)
