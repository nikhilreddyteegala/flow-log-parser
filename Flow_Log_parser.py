from __future__ import print_function
import csv
from collections import defaultdict, namedtuple
import sys
import logging
from typing import Dict, List, NamedTuple

# For Python 2 and 3 compatibility
if sys.version_info[0] >= 3:
    unicode = str

# Configure the logger
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

PortProtocol = namedtuple('PortProtocol', ["Port", "Protocol"])

class FlowLogProcessorRun:

    def __init__(self,
                 protocol_index_file_path: str,
                 port_protocol_tag_file_path: str):
        self.protocol_index_map: Dict[int, str] = \
            self.create_protocol_index_map(protocol_index_file_path)
        self.protocol_reverse_idx_map: Dict[str, int] = {
            value: key for key, value in self.protocol_index_map.items()
        }
        self.port_protocol_tag_map: Dict[PortProtocol, str] = \
            self.create_port_protocol_tag_map(port_protocol_tag_file_path, self.protocol_reverse_idx_map)

    def create_protocol_index_map(self, file_path: str) -> Dict[int, str]:
        protocol_map = defaultdict(lambda: -1)
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                protocol_range = row['index']
                protocol_name: str = str(row['protocol']).lower()
                
                # Check if the protocol index is a range (e.g., '146-252')
                if '-' in protocol_range:
                    start, end = map(int, protocol_range.split('-'))
                    for protocol_index in range(start, end + 1):
                        protocol_map[protocol_index] = protocol_name
                else:
                    # It's a single protocol index
                    protocol_index: int = int(protocol_range)
                    protocol_map[protocol_index] = protocol_name
        return protocol_map

    def create_port_protocol_tag_map(self, file_path: str, protocol_idx_reverse_map: Dict[str, int]) -> Dict[PortProtocol, str]:
        port_protocol_tag_map: Dict[PortProtocol, str] = {}
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                port: int = int(row['dstport'])
                protocol_name: str = row['protocol'].lower()
                tag: str = row['tag']
                if protocol_name not in protocol_idx_reverse_map:
                    logging.warning(f"Missing entry for {protocol_name} in protocol map.")
                    protocol_index: int = -1
                else:
                    protocol_index = protocol_idx_reverse_map[protocol_name]
                port_protocol: PortProtocol = PortProtocol(port, protocol_index)
                if port_protocol in port_protocol_tag_map:
                    logging.warning(f"Multiple entries for port_protocol {port_protocol} with "
                                    f"values = [{port_protocol_tag_map[port_protocol]}, {tag}]")
                port_protocol_tag_map[port_protocol] = tag
        return port_protocol_tag_map

    def get_counts_from_flow_logs(self, flow_logs_file_path: str,
                                  port_protocol_tag_map: Dict[PortProtocol, str]) -> (
            Dict[str, int],
            Dict[PortProtocol, int]
    ): # type: ignore
        tag_counts = defaultdict(int)
        port_protocol_counts = defaultdict(int)
        total_entries = 0

        def parse_flow_log(log_line):
            parts = log_line.split()
            if len(parts) < 14:
                return None
            return {
                'dstport': int(parts[6]),
                'protocol': int(parts[7])
            }

        logging.info("\nProcessing flow logs:")
        with open(flow_logs_file_path, 'r') as log_file:
            for line in log_file:
                flow = parse_flow_log(line)
                if flow:
                    total_entries += 1
                    port, protocol_idx = flow['dstport'], flow['protocol']
                    port_protocol = PortProtocol(port, protocol_idx)
                    tag = port_protocol_tag_map.get(port_protocol, 'Untagged')
                    if tag != 'Untagged':
                        tag_counts[tag] += 1
                    port_protocol_counts[port_protocol] += 1
                    logging.info(f"Log entry - Port: {port}, Protocol: {self.protocol_index_map.get(protocol_idx, 'unknown')}, Tag: {tag}")

        tag_counts['Untagged'] = total_entries - sum(tag_counts.values())

        return tag_counts, port_protocol_counts

    def write_counters_to_file(self, tag_counter: Dict[str, int],
                           port_protocol_counter: Dict[PortProtocol, int],
                           output_file_path: str):
        with open(output_file_path, 'w') as output_file:
            # Write tag counts
            output_file.write("Tag Counts:\n")
            output_file.write("Tag,Count\n")
            
            # Sort tags by count (descending) and alphabetically, but exclude 'Untagged'
            sorted_tags = sorted(
                [(tag, count) for tag, count in tag_counter.items() if tag != 'Untagged'],
                key=lambda x: (-x[1], x[0])
            )
            
            # Write sorted tags
            for tag, count in sorted_tags:
                output_file.write(f"{tag},{count}\n")
            
            # Write 'Untagged' at the end if it exists
            if 'Untagged' in tag_counter:
                output_file.write(f"Untagged,{tag_counter['Untagged']}\n")

            # Write Port Protocol Counts (unchanged)
            output_file.write("\nPort/Protocol Combination Counts:\n")
            output_file.write("Port,Protocol,Count\n")
            for (port, protocol), count in sorted(port_protocol_counter.items(), key=lambda x: (x[0][0], x[0][1])):
                protocol_name = self.protocol_index_map.get(protocol, str(protocol))
                output_file.write(f"{port},{protocol_name},{count}\n")

    def process(self, flow_logs_file_path: str, output_file_path: str):
        tag_counter, port_protocol_counter = self.get_counts_from_flow_logs(
            flow_logs_file_path,
            self.port_protocol_tag_map
        )
        self.write_counters_to_file(tag_counter, port_protocol_counter, output_file_path)

if __name__ == "__main__":
    flow_log_processor = FlowLogProcessorRun(
        protocol_index_file_path="protocol-numbers-1.csv",
        port_protocol_tag_file_path="lookup_table.csv",
    )

    flow_log_processor.process("flow_logs.txt", "output.txt")