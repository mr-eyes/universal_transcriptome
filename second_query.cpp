#include "sqliteManager.hpp"
#include "string"
#include "kDataFrame.hpp"
#include "INIReader.h"
#include <glob.h>
#include <sstream>
#include <stdexcept>
#include "omnigraph.hpp"
#include "tuple"
#include <sys/stat.h>
#include <fstream>

using namespace std;
using namespace phmap;

string getFileName(const string &s) {

    char sep = '/';

#ifdef _WIN32
    sep = '\\';
#endif

    size_t i = s.rfind(sep, s.length());
    if (i != string::npos) {
        return (s.substr(i + 1, s.length() - i));
    }

    return ("");
}


vector<string> glob(const string &pattern) {
    using namespace std;

    // glob struct resides on the stack
    glob_t glob_result;
    memset(&glob_result, 0, sizeof(glob_result));

    // do the glob operation
    int return_value = glob(pattern.c_str(), GLOB_TILDE, NULL, &glob_result);
    if (return_value != 0) {
        globfree(&glob_result);
        stringstream ss;
        ss << "glob() failed with return_value " << return_value << endl;
        throw runtime_error(ss.str());
    }

    // collect all the filenames into a list<string>
    vector<string> filenames;
    for (size_t i = 0; i < glob_result.gl_pathc; ++i) {
        filenames.push_back(string(glob_result.gl_pathv[i]));
    }

    // cleanup
    globfree(&glob_result);

    // done
    return filenames;
}

string create_dir(string output_file, int serial) {
    int dir_err;
    string new_name = "";

    if (!serial) {
        dir_err = mkdir(output_file.c_str(), S_IRWXU | S_IRWXG | S_IROTH | S_IXOTH);
        new_name = output_file;
    } else {
        new_name = output_file + "_v." + to_string(serial);
        dir_err = mkdir(new_name.c_str(), S_IRWXU | S_IRWXG | S_IROTH | S_IXOTH);
    }

    if (-1 == dir_err) return create_dir(output_file, ++serial);

    return new_name;
}

const string prepare_update(int ID, int seq1_original_component, int seq2_original_component) {
    const string _sqlite_update = "UPDATE reads SET "
                                  "seq1_original_component=" + to_string(seq1_original_component)
                                  + ", seq2_original_component=" + to_string(seq2_original_component)
                                  + " WHERE ID=" + to_string(ID) + ";";

    return _sqlite_update;
}

class fileHandler {

public:
    ofstream fileStream;

    fileHandler(string &filename) {
        this->fileStream.open(filename);
    }

    void write(string &line) {
        this->fileStream << line;
    }

    void close() {
        fileStream.close();
    }

};

int main() {

    string config_file_path = "../config.ini";
    string index_prefix, PE_1_reads_file, PE_2_reads_file, sqlite_db, collective_comps_indexes_dir, fasta_out;
    int batchSize, kSize, no_of_sequences;

    INIReader reader(config_file_path);

    if (reader.ParseError() != 0) {
        cout << "Can't load '" << config_file_path << "'\n";
        return 1;
    }


    index_prefix = reader.Get("kProcessor", "idx_prefix", "");
    collective_comps_indexes_dir = reader.Get("kProcessor", "collective_comps_indexes_dir", "");
    PE_1_reads_file = reader.Get("Reads", "read1", "");
    PE_2_reads_file = reader.Get("Reads", "read2", "");
    no_of_sequences = reader.GetInteger("Reads", "seqs_no", 0);
    sqlite_db = reader.Get("SQLite", "db_file", "query1_result.db");
    fasta_out = reader.Get("output_fasta", "fasta_dir", "fasta_out");
    batchSize = reader.GetInteger("kProcessor", "chunk_size", 1);
    kSize = reader.GetInteger("kProcessor", "ksize", 31);

    cerr << "Fetch kProcessor indexes paths ..." << endl;

    vector<string> filenames = glob(collective_comps_indexes_dir);
    map<int, string> index_paths;

    int collectiveComps_no = filenames.size();

    // Create fasta files handlers, {R1,2: {comp : path}}
    map<int, map<int, fileHandler * >> fasta_writer;

    // create main dir
    string out_dir = create_dir(fasta_out, 0);

    // create PE1 directory
    string R1_dir = create_dir(out_dir + "/" + "R1", 0);

    // create PE2 directory
    string R2_dir = create_dir(out_dir + "/" + "R2", 0);

    map<int, string> R_dirs = {
            {1, R1_dir},
            {2, R2_dir}
    };

    // Creating fasta files (2xCollectiveCompsNo)
    for (int R = 1; R <= 2; R++) {
        for (int compID = 1; compID <= collectiveComps_no; compID++) {
            string file_name = R_dirs[R] + "/" + to_string(compID) + ".fa";
            fasta_writer[R][compID] = new fileHandler(file_name);
        }
    }


    for (auto &filename : filenames) {
        string _base_name, _index_prefix;
        _base_name = getFileName(filename);
        int idx_no = stoi(_base_name.substr(4, 3));
        _index_prefix.append(filename + "/" + _base_name);
        index_paths[idx_no] = _index_prefix;
    }

    kDataFrame *kf;
    Omnigraph *second_query = new Omnigraph();
    kmerDecoder *KD = new Kmers(kSize);
    vector<kmer_row> kmers;

    string db_file;
    auto *SQL = new SQLiteManager(sqlite_db);

    // Make it faster
    string _sqlite_sync = "PRAGMA synchronous = OFF;";
    SQL->rc = sqlite3_exec(SQL->db.db_, _sqlite_sync.c_str(), SQL->callback, 0, &SQL->zErrMsg);

    map<int, string> queries = {
            {1, "SELECT ID, PE_seq1 FROM reads WHERE seq1_collective_component="},
            {2, "SELECT ID, PE_seq2 FROM reads WHERE seq2_collective_component="},
    };

    const string _sqlite_update = "UPDATE reads SET "
                                  "seq1_original_component=" + to_string(1)
                                  + " WHERE ID=" + to_string(1) + ";";

    for (const auto &idx : index_paths) {
        int collectiveCompID = idx.first;
        kf = kDataFrame::load(idx.second);

        cerr << "Processing collective component (" << idx.first << ") ... ";
        chrono::high_resolution_clock::time_point t1 = chrono::high_resolution_clock::now();

        for (int R_ID = 1; R_ID <= 2; R_ID++) {
            const string _sqlite_select = queries[R_ID] + to_string(idx.first) + ";";

            sqlite3pp::query qry(SQL->db, _sqlite_select.c_str());

            // Iterate over the database reads
            for (sqlite3pp::query::iterator i = qry.begin(); i != qry.end(); ++i) {
                int ROW_ID;
                const char *PE_seq;

                tie(ROW_ID, PE_seq) = (*i).get_columns < int, char const* > (0, 1);

                string seq = PE_seq;
                KD->seq_to_kmers(seq, kmers);
                tuple<string, bool, int, uint64_t> read_result = second_query->classifyRead(kf, kmers,
                                                                                            R_ID);

                string constructedRead = get<0>(read_result);
                bool mapped_flag = get<1>(read_result);
                int seq_original_component = get<2>(read_result);

                    // Header (R_ID|CompID)
                    string fasta_read = ">" + to_string(ROW_ID) + "|" + to_string(seq_original_component) + "\n";

                    // Read
                    fasta_read.append(constructedRead + "\n");

                    // Write
                    fasta_writer[R_ID][collectiveCompID]->write(fasta_read);

            }


        }

        chrono::high_resolution_clock::time_point t2 = chrono::high_resolution_clock::now();
        auto milli = chrono::duration_cast<chrono::milliseconds>(t2 - t1).count();
        long hr = milli / 3600000;
        milli = milli - 3600000 * hr;
        long min = milli / 60000;
        milli = milli - 60000 * min;
        long sec = milli / 1000;
        milli = milli - 1000 * sec;
        cout << " Done in " << min << ":" << sec << ":" << milli << endl;

        delete kf;
    }

    delete KD;
    SQL->close();

    // Closing all fasta files
    for (int R = 1; R <= 2; R++) {
        for (int compID = 1; compID <= collectiveComps_no; compID++) {
            fasta_writer[R][compID]->close();
        }
    }


    return 0;
}