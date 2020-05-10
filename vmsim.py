#!/usr/bin/env python3
import sys

class Page:
    def __init__(self, address, offset_bits):
        self.offset = offset_bits
        self.page_number = address >> self.offset

    def getPageNumber(self):
        return self.page_number

    def contains(self, address):
        return self.page_number == address >> self.offset

class PageTableEntry:
    def __init__(self, offset_bits):
        self.offset = offset_bits
        self.page = None
        self.dirty = False
        self.most_recent_access = 0
        self.num_accesses = 0
        self.second_chance = False

    def getPage(self):
        return self.page

    def setPage(self, address):
        self.page = Page(address, self.offset)
        self.second_chance = False

    def hasPage(self):
        return self.page != None

    def isDirty(self):
        return self.dirty

    def hasSecondChance(self):
        """
        Returns:
            True if page has been accessed since last considered for replacement
        """
        return self.second_chance

    def losesChance(self):
        """
        Sets second chance bit to 0
        """
        self.second_chance = False

    def access(self, access_type, access_index):
        """
        Marks current PageTableEntry as accessed and sets LRU and Second Chance information
        """
        if access_type == 'l':
            self.load(access_index)
        elif access_type == 's':
            self.store(access_index)
        else:
            raise ValueError('Invalid access type: "{}", expected "l" or "s"'.format(access_type))

    def load(self, access_index):
        self.most_recent_access = access_index
        self.num_accesses += 1

    def store(self, access_index):
        self.most_recent_access = access_index
        self.dirty = True

    def clear(self):
        """
        Clears out page from page table entry
        """
        self.page = None
        self.dirty = False
        self.most_recent_access = 0
        self.num_accesses = 0

class PageTable:
    def __init__(self, num_frames, page_size, trace_indices):
        self.size = num_frames
        self.table = [PageTableEntry(page_size) for i in range(self.size)]
        self.page_faults = 0
        self.writes_to_disk = 0
        self.trace_indices = trace_indices

    def query(self, address, access_type, index):
        """
        Checks if data from address is stored in PageTable.
        If it is, update LRU and Second Chance info.
        If not, a page fault is encountered and an entry is removed from the
        PageTable and the new address is loaded in.

        Args:
            address: Address being accessed
            access_type: Load or Store
            index: Number of memory accesses
        """
        pte = self.getTableEntryByAddress(address)
        if pte:
            # Memory location exists in page table
            pte.access(access_type, index)
            pte.second_chance = True
        else:
            # Memory location does not exist in page table
            # An old page must be evicted and new one must be loaded into memory
            pte = self.evictAndLoad(address, index)
            pte.access(access_type, index)
            self.page_faults += 1

    def evictAndLoad(self, address, index):
        """
        Checks if there is an empty spot in PageTable.
        If not, remove an entry and load in the new one

        Args:
            address: Address to be loaded in
            index: Number of memory accesses

        Returns:
            PageTableEntry containing address
        """
        if self.tableIsFull():
            self.evict(index)
        return self.load(address)

    def evict(self):
        # This method will change based on eviction algorithm
        pass

    def load(self, address):
        """
        Finds empty spot in PageTable and loads address into it

        Args:
            address: Address to be loaded in

        Returns:
            PageTableEntry containing address
        """
        for entry in self.table:
            if not entry.hasPage():
                entry.setPage(address)
                return entry
        raise RuntimeError("Attempting to load page into table, but there's no room")

    def tableIsFull(self):
        """
        Returns:
            True if no open spots in PageTable, otherwise False
        """
        for entry in self.table:
            if not entry.hasPage():
                return False
        return True

    def clearEntry(self, entry):
        """
        Removes entry from PageTable and writes it to disk if it's dirty

        Args:
            entry: Entry to be removed
        """
        if entry.isDirty():
            self.writes_to_disk += 1
        entry.clear()

    def getTableEntryByAddress(self, address):
        """
        If PageTable contains address, return PageTableEntry that contains it,
        Otherwise return None

        Args:
            address: Address to be checked

        Returns:
            PageTableEntry containing address or None
        """
        for entry in self.table:
            if entry.hasPage():
                if entry.getPage().contains(address):
                    return entry
        return None

    def entryNextUsedAt(self, page_table_entry, index):
        """
        Finds the next time a PageTableEntry is accessed. Used for OPT
        replacement algorithm

        Args:
            page_table_entry: PageTableEntry being checked
            index: Current memory access number

        Returns:
            Next index the current PageTableEntry is accessed at.
        """
        page_used_at = self.trace_indices[page_table_entry.getPage().getPageNumber()]
        first_element_greater_than = self.findFirstElementGreaterThan(page_used_at, index)
        if first_element_greater_than == -1:
            raise ValueError('No element in array > index')
        return page_used_at[self.findFirstElementGreaterThan(page_used_at, index)]

    def findFirstElementGreaterThan(self, array, index):
        """
        Binary search to find first element in array greater than index

        Args:
            index: Current memory access number
            array: Array containing every index an address is referenced at

        Returns:
            First value in array greater than index. If index is greater than
            every value in array, return -1
        """
        l, r = 0, len(array) - 1
        ans = -1;
        while (l <= r):
            mid = l + (r - l) // 2;
            # Move to right side if target is greater
            if (array[mid] <= index):
                l = mid + 1;
            # Move left side.
            else:
                ans = mid;
                r = mid - 1;
        return ans;

    def entryIsNotUsedAgain(self, page_table_entry, index):
        """
        Returns True if a Page will be accessed again in the future.
        This is only used in the OPT replacement algorithm.
        """
        return self.trace_indices[page_table_entry.getPage().getPageNumber()][-1] < index


class OptimalTable(PageTable):
    def __init__(self, num_frames, page_size, trace_indices):
        super().__init__(num_frames, page_size, trace_indices)

    def evict(self, index):
        """
        PageTable eviction method for OPT replacement algorithm.
        Removes Page from PageTable that will be latest in the future.
        If multiple Pages will never be used again, use LRU replacement between them.

        Args:
            index: Current memory access number
        """

        # Find the pages in the page table that are never used again (if any)
        never_used_again = [entry for entry in self.table if self.entryIsNotUsedAgain(entry, index)]

        # If there are addresses that are never used again, use LRU to evict them
        if len(never_used_again) > 0:
            least_recently_used = never_used_again[0]
            for entry in never_used_again[1:]:
                if entry.most_recent_access < least_recently_used.most_recent_access:
                    least_recently_used = entry
            self.clearEntry(least_recently_used)
        else:
            next_used = [self.entryNextUsedAt(entry, index) for entry in self.table]
            used_latest = self.table[next_used.index(max(next_used))]
            self.clearEntry(used_latest)



class LRUTable(PageTable):
    def __init__(self, num_frames, page_size, trace_indices):
        super().__init__(num_frames, page_size, trace_indices)

    def evict(self, index):
        """
        PageTable eviction method for LRU replacement algorithm.
        Removes Page from PageTable that has been used the least recently.

        Args:
            index: Current memory access number
        """
        least_recently_used = self.table[0]
        for entry in self.table[1:]:
            if entry.most_recent_access < least_recently_used.most_recent_access:
                least_recently_used = entry
        self.clearEntry(least_recently_used)

class SecondChanceTable(PageTable):
    def __init__(self, num_frames, page_size, trace_indices):
        super().__init__(num_frames, page_size, trace_indices)
        self.round_robin_index = -1

    def evict(self, index):
        """
        PageTable eviction method for Second Chance replacement algorithm.
        Pages are removed in a round robin fashion, however a page is given a
        "second chance" if it has been accessed since the last time it was
        considered for eviction.

        Args:
            index: Current memory access number
        """
        nothing_has_been_evicted = True
        while nothing_has_been_evicted:
            self.round_robin_index = (self.round_robin_index + 1) % self.size
            if self.table[self.round_robin_index].hasSecondChance():
                self.table[self.round_robin_index].losesChance()
            else:
                self.clearEntry(self.table[self.round_robin_index])
                nothing_has_been_evicted = False

class VirtualMemorySimulator:
    def __init__(self, trace_file, num_frames, eviction_type, offset_bits):
        """
        Initializes virtual memory simulation on input trace_file.
        Each memory access in trace_file is given an index value based on the order
        of the trace_file. These indices are used for keeping track of least recently
        used and opt replacements.

        Args:
            trace_file: Text file containing memory addresses
            num_frames: Number of page table entries in the page table
            eviction_type: Eviction algorithm used in simulation
            offset_bits: Number of offset bits in memory address
        """
        self.source_file = trace_file
        self.offset_bits = offset_bits

        mem_accesses = 0
        trace_indices = {}

        with open(self.source_file) as file:
            for index, mem_access in enumerate(file):
                mem_accesses += 1
                if eviction_type == 'opt':
                    address = int(mem_access.split(' ')[1], 16)
                    page_number = address >> self.offset_bits
                    if page_number in trace_indices:
                        trace_indices[page_number].append(index)
                    else:
                        trace_indices[page_number] = [index]

        self.mem_accesses = mem_accesses
        self.page_table = self.createPageTable(num_frames, offset_bits, eviction_type, trace_indices)

    def createPageTable(self, num_frames, offset_bits, eviction_type, trace_indices):
        """
            Initializes PageTable based on user specified eviction method

            Returns:
                PageTable
        """
        if eviction_type == 'opt':
            return OptimalTable(num_frames, offset_bits, trace_indices)
        elif eviction_type == 'lru':
            return LRUTable(num_frames, offset_bits, trace_indices)
        elif eviction_type == 'second':
            return SecondChanceTable(num_frames, offset_bits, trace_indices)
        else:
            raise ValueError('Invalid Eviction Type "{}", should be "opt", "lru", or "second"'.format(eviction_type))

    def run(self):
        """
        Iterates over memory accesses in trace file and runs simulation

        Returns:
            Dictionary containing run statistics including total number of memory
            accesses, number of page faults encountered, and number of writes to
            the disk.
        """
        with open(self.source_file) as file:
            for index, mem_access in enumerate(file):
                access_type = mem_access.split(' ')[0]
                address = int(mem_access.split(' ')[1], 16)
                self.page_table.query(address, access_type, index)
        return {"memory_accesses": self.mem_accesses,
                "page_faults": self.page_table.page_faults,
                "writes_to_disk": self.page_table.writes_to_disk}


if __name__ == "__main__":
    args = sys.argv
    num_frames = int(args[2])
    mode = args[4]
    trace_file = args[5]
    offset_bits = 12 # 4 KB frame size

    simulator = VirtualMemorySimulator(trace_file, num_frames, mode, offset_bits)
    statistics = simulator.run()

    print("Algorithm: {}".format(mode.upper()))
    print("Number of frames: {}".format(num_frames))
    print("Total memory accesses: {}".format(statistics["memory_accesses"]))
    print("Total page faults: {}".format(statistics["page_faults"]))
    print("Total writes to disk: {}".format(statistics["writes_to_disk"]))
