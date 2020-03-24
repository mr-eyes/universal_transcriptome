#include <iostream>
#include <kDataFrame.hpp>
#include <string>
#include <vector>
#include <cstdint>
#include <algorithms.hpp>

using namespace std;

string kmers_to_seq(vector<string> & kmers){
    string seq;
    int kSize = kmers[0].size();
    int i;
    for(i = 0; i < kmers.size(); i+= kSize)
        seq += kmers[i];

    return seq.substr(0, (kmers.size() - 1)) + kmers.back();
}

int main(int argc, char **argv) {

    string index_prefix = "data/idx_cDBG_SRR11015356_k31unitigs/idx_idx_cDBG_SRR11015356_k31unitigs";
    string PE_1_reads_file = "data/SRR11015356_1.fasta";
    string PE_2_reads_file = "data/SRR11015356_2.fasta";

    int kSize = 31;
    int chunk_size = 1;
    int no_chunks = 67954363 / chunk_size;

    colored_kDataFrame *ckf = colored_kDataFrame::load(index_prefix);
    kDataFrame *kf = ckf->getkDataFrame();

    kmerDecoder *READS_KMERS = new Kmers(PE_1_reads_file, chunk_size, kSize);

    int Reads_chunks_counter = no_chunks;

    while (!READS_KMERS->end()) {
        READS_KMERS->next_chunk();
        // --Reads_chunks_counter;
        // cerr << Reads_chunks_counter << " remain chunks ..." << endl;

        for (const auto &seq: *READS_KMERS->getKmers()) {
            uint64_t color1 = kf->getCount(seq.second.front().hash);
            uint64_t color2 = kf->getCount(seq.second.back().hash);

            if (color1 != 0 && color2 != 0) {

                if (color1 == color2) {
                    cout << seq.first << '\t' << 1 << '\t' << "0:-1" << endl;
                } else {
                    cout << seq.first << '\t' << 0 << '\t' << "0:0" << endl;
                }
            } else {
                // That mean both are zeros so both could not be found
                int noKmers = seq.second.size();
                vector<uint64_t> all_colors(noKmers);

                phmap::flat_hash_set<uint64_t> unique_colors;
                phmap::flat_hash_map<bool, int> found_count;

                // Get all the colors
                for (const auto &kmer: seq.second) {
                    uint64_t color = kf->getCount(kmer.hash);
                    found_count[bool(color)]++;
                    all_colors.push_back(color);
                    unique_colors.insert(color);
                }

                // Check found Vs. unfound
                if ((found_count[0] / noKmers) < 0.5) {
                    // not aligned read
                    cout << seq.first << '\t' << 0 << '\t' << "0:0" << endl;
                } else {
                    if (unique_colors.size() > 2) {
                        // unfound = 0, found = !0, so if all the kmers are coming from single component then the unique number of colors should be 2
                        cout << seq.first << '\t' << 0 << '\t' << "0:0" << endl;
                    } else {
                        int start_kmer, end_kmer, i, j;
                        i = 0;
                        j = 0;
                        auto it = all_colors.begin();

                        while (it != all_colors.end()) {
                            i++;
                            if (*it != 0) {
                                start_kmer = i;
                                auto rev_it = all_colors.end();
                                while (rev_it != it) {
                                    j--;
                                    if (*rev_it != 0) {
                                        end_kmer = j;
                                        it = all_colors.end();
                                        break;
                                    }
                                    --rev_it;
                                }
                            }
                            ++it;
                        }
                        cout << seq.first << '\t' << 1 << '\t' << start_kmer << ':' << end_kmer << endl;
                    }
                }
            }
        }
    }

    return 0;
}