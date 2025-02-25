#!/usr/bin/env python3
import os
import shutil
import xml.etree.ElementTree as ET
import re

def print_error(msg):
    # Prints error messages with 4-space indent in red.
    print("    \033[31m" + msg + "\033[0m")

def sanitize_filename(name):
    """
    Remove or replace characters that are not allowed in filenames.
    This replaces characters like \ / : * ? " < > | with an underscore.
    """
    return re.sub(r'[\\/:"*?<>|]+', '_', name)

def parse_files_xml(files_xml_path):
    """
    Parse the ./files.xml and return a mapping from contextid to a tuple (contenthash, file_extension)
    using only file entries with a valid contenthash and a filename that is not just '.'.
    """
    files_by_contextid = {}
    try:
        tree = ET.parse(files_xml_path)
    except Exception as e:
        print_error(f"Error parsing {files_xml_path}: {e}")
        return files_by_contextid

    root = tree.getroot()
    for file_elem in root.findall("file"):
        contextid_elem = file_elem.find("contextid")
        contenthash_elem = file_elem.find("contenthash")
        filename_elem = file_elem.find("filename")
        if contextid_elem is None or contenthash_elem is None or filename_elem is None:
            continue

        contextid = contextid_elem.text.strip()
        contenthash = contenthash_elem.text.strip() if contenthash_elem.text else ""
        filename = filename_elem.text.strip() if filename_elem.text else ""

        # Skip if no valid contenthash or filename is just '.'
        if not contenthash or filename == "." or not filename:
            continue

        # Extract file extension (everything after the last period)
        if '.' in filename:
            extension = filename.split('.')[-1]
        else:
            extension = ""

        # Save the file info if an extension is available.
        if extension and contextid not in files_by_contextid:
            files_by_contextid[contextid] = (contenthash, extension)
    return files_by_contextid

def process_sections(files_by_contextid):
    sections_dir = "./sections"
    activities_dir = "./activities"
    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)

    # Iterate over each subfolder in ./sections
    for subfolder in os.listdir(sections_dir):
        subfolder_path = os.path.join(sections_dir, subfolder)
        if not os.path.isdir(subfolder_path):
            continue

        section_xml_path = os.path.join(subfolder_path, "section.xml")
        if not os.path.exists(section_xml_path):
            print_error(f"section.xml not found in {subfolder_path}")
            continue

        try:
            tree = ET.parse(section_xml_path)
        except Exception as e:
            print_error(f"Error parsing {section_xml_path}: {e}")
            continue

        root_section = tree.getroot()
        number_elem = root_section.find("number")
        name_elem = root_section.find("name")
        sequence_elem = root_section.find("sequence")
        if number_elem is None or name_elem is None or sequence_elem is None:
            print_error(f"Missing required element(s) in {section_xml_path}")
            continue

        section_number_text = number_elem.text.strip() if number_elem.text else "0"
        section_name = name_elem.text.strip() if name_elem.text else "Unnamed"
        sequence_text = sequence_elem.text.strip() if sequence_elem.text else ""

        try:
            section_number_int = int(section_number_text)
        except ValueError:
            section_number_int = 0

        # Create a folder for the section.
        # Folder name format: "XX Chapter {section_name}" (with XX being the zero-padded section number).
        folder_name = f"{section_number_int:02d} Chapter {sanitize_filename(section_name)}"
        section_output_path = os.path.join(output_dir, folder_name)
        os.makedirs(section_output_path, exist_ok=True)

        # Process each sequence ID (comma-separated) in order.
        sequence_ids = [s.strip() for s in sequence_text.split(",") if s.strip()]
        for idx, seq_id in enumerate(sequence_ids, start=1):
            xml_file = None
            xml_type = None  # "resource" or "page"

            # Try resource folder first.
            resource_folder = os.path.join(activities_dir, f"resource_{seq_id}")
            resource_xml_path = os.path.join(resource_folder, "resource.xml")
            if os.path.exists(resource_xml_path):
                xml_file = resource_xml_path
                xml_type = "resource"
            else:
                # Try page folder.
                page_folder = os.path.join(activities_dir, f"page_{seq_id}")
                page_xml_path = os.path.join(page_folder, "page.xml")
                if os.path.exists(page_xml_path):
                    xml_file = page_xml_path
                    xml_type = "page"
                else:
                    # Check for any folder ending with _{seq_id} that is not resource_ or page_.
                    found_other = None
                    for folder in os.listdir(activities_dir):
                        folder_path = os.path.join(activities_dir, folder)
                        if not os.path.isdir(folder_path):
                            continue
                        if folder.endswith(f"_{seq_id}") and not (folder.startswith("resource_") or folder.startswith("page_")):
                            found_other = folder
                            break
                    if found_other is not None:
                        prefix = found_other.split("_")[0]
                        print_error(f"Skipping because it is {prefix} and not page or resource")
                    else:
                        print_error(f"Resource/page folder not found for sequence {seq_id}")
                    continue  # Skip this sequence

            # Process the XML file (either resource.xml or page.xml)
            try:
                tree_xml = ET.parse(xml_file)
            except Exception as e:
                print_error(f"Error parsing {xml_file}: {e}")
                continue

            root_xml = tree_xml.getroot()
            contextid = root_xml.attrib.get("contextid")
            if not contextid:
                print_error(f"Missing contextid attribute in {xml_file}")
                continue

            # Get the <resource> or <page> element.
            child_elem = root_xml.find(xml_type)
            if child_elem is None:
                print_error(f"Missing <{xml_type}> element in {xml_file}")
                continue

            name_elem_resource = child_elem.find("name")
            if name_elem_resource is None or not name_elem_resource.text:
                print_error(f"Missing {xml_type} name in {xml_file}")
                continue

            resource_name = name_elem_resource.text.strip()

            # Look up file info using contextid from files.xml mapping.
            file_info = files_by_contextid.get(contextid)
            if not file_info:
                print_error(f"No file info found for contextid {contextid} in {xml_file}")
                continue

            contenthash, extension = file_info
            # Construct the source file path: "./files/{first two chars of contenthash}/{contenthash}"
            source_file_path = os.path.join("./files", contenthash[:2], contenthash)
            if not os.path.exists(source_file_path):
                print_error(f"Source file not found: {source_file_path} for {xml_type} '{resource_name}'")
                continue

            # Destination file name: "XX {resource_name}.{extension}" (XX is the ordinal, zero-padded)
            dest_filename = f"{idx:02d} {sanitize_filename(resource_name)}.{extension}"
            dest_file_path = os.path.join(section_output_path, dest_filename)

            try:
                shutil.copy2(source_file_path, dest_file_path)
                print(f"Copied: {source_file_path} --> {dest_file_path}")
            except Exception as e:
                print_error(f"Error copying file from {source_file_path} to {dest_file_path}: {e}")

def main():
    files_xml_path = "./files.xml"
    if not os.path.exists(files_xml_path):
        print_error(f"{files_xml_path} not found!")
        return

    files_by_contextid = parse_files_xml(files_xml_path)
    if not files_by_contextid:
        print_error("No valid file entries found in files.xml")
        return

    process_sections(files_by_contextid)

if __name__ == "__main__":
    main()

