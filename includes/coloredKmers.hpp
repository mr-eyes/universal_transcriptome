#ifndef OMNIGRAPH_COLOREDKMERS_HPP
#define OMNIGRAPH_COLOREDKMERS_HPP

#include <parallel_hashmap/phmap.h>
#include <kmerDecoder.hpp>
#include <iostream>
#include <cstdint>
#include <string>

using phmap::flat_hash_map;
using namespace std;

class ColoredKmers {


public:
    flat_hash_map<uint64_t, uint32_t> kmers;
    flat_hash_map<uint32_t, uint32_t> unitigToComponent;
    flat_hash_map<char, uint32_t> metadata;
    int original_inserted_kmers;
    kmerDecoder *KD;

    ColoredKmers() {

    }

    ColoredKmers(const string &namesToGroupsFile, int kSize, int hashing_mode);

    uint32_t getKmerColor(const string &kmer_str);

    void setKmerColor(uint64_t kmer_hash, uint32_t & unitig_id);
    void setKmerColor(string & kmer_str, uint32_t & unitig_id);

    static ColoredKmers *load(const string &prefix);

    void load_names(const string &names_tsv_path);

    void *save(const string &prefix);

    int size();

    double get_error_rate() {
        return 100 * ((double) this->original_inserted_kmers / (double) this->kmers.size());
    }

    unsigned long get_error_kmers() {
        return this->original_inserted_kmers - this->kmers.size();
    }

    int get_seqs_number(){
        return this->unitigToComponent.size();
    }

};


#endif //OMNIGRAPH_COLOREDKMERS_HPP
