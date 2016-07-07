#! /usr/bin/env python2

# from Bio import Entrez
from sys import exit
import pickle
from difflib import SequenceMatcher
from itertools import islice
from RecBlastUtils import *
# from RecBlastParams import *


all_genes_dict = {}


# find similarity between sequences
def similar(a, b):
    """
    Evaluates similarity ratio between a and b.
    :param a: string
    :param b: string
    :return: similarity ratio
    """
    return SequenceMatcher(None, a, b).ratio()


def format_description(description, regex, species):
    """

    :param description:
    :param regex:
    :param species:
    :return:
    """
    species = lower(str(species))
    description = replace(lower(str(description)), "predicted: ", "")
    description = replace(description, "[{}]".format(species), "")
    description = replace(description, "{}".format(species), "")
    description = replace(description, "unnamed protein product", "")
    description = replace(description, "isoform", "")
    description = strip(re_sub(regex, '', description))
    return description


# structure of update_match_results:
# {gene_name: { animal1: [ [strict, not strict] ],  animal2: [],  animal3 = [], ...}}
def update_match_results(enumerator, animal_org, target_name1, this_gene_dic, is_rbh, DEBUG, debug):
    """
    Prints final update_match_results for each gene
    :param is_rbh: True if the value is RBH, False if not.
    :param this_gene_dic:
    :param enumerator: result number for gene_id
    :param animal_org:  Name of the organism
    :param target_name1:  Target gene name
    :param DEBUG:  The debug flag (True/False)
    :param debug:  The debug function
    :return:
    """
    try:  # update current animal
        this_gene_dic[animal_org][1] += 1  # non strict increments anyway
        if enumerator == 1:  # strict increment
            this_gene_dic[animal_org][0] += 1

    except KeyError:  # if we don't have animal_org in our db
        if enumerator == 1:  # if it is the first match
            if is_rbh:
                this_gene_dic[animal_org] = [1, 1, 1]
            else:
                this_gene_dic[animal_org] = [1, 1, 0]
        elif enumerator > 1:  # found match, not first
            this_gene_dic[animal_org] = [0, 1, 0]

    debug("current status for gene %s, animal %s: %s" % (target_name1, animal_org, this_gene_dic[animal_org]))
    return True


def write_all_output_csv(out_dict, org_list, csv_out_filename, DEBUG, debug):
    """
    Writes formatted final output to CSV.
    :param out_dict: a dictionary of dictionaries
    :param org_list: a list of organisms
    :param csv_out_filename:
    :param DEBUG:
    :param debug:
    :return:
    """
    # get all organisms
    all_org_list = list(set(org_list))
    # TODO: decide how to sort them (alphabetically?)
    with open(csv_out_filename, 'w') as csv_file:
        csv_file.write(",".join(["gene_name"] + all_org_list))  # write header
        csv_file.write("\n")
        for gene_name in out_dict:  # write every line
            assert type(gene_name) == str, "Gene name is not a string!"
            out_line = [gene_name]  # initialize output line: each line starts with the gene name
            for org in all_org_list:
                try:
                    debug(out_dict[gene_name][org])
                    out_line.append(out_dict[gene_name][org])
                # if the value doesn't exist for the animal - leave it empty
                except KeyError:
                    out_line.append("")
                    # out_line.append("[0-0-0]")  # if we want the output that way...
            # formatting and printing the line
            out_line = [replace(str(x), ', ', '-') for x in out_line]
            csv_file.write(",".join(out_line))
            csv_file.write("\n")
            debug("Printed gene_name {0} to output file".format(gene_name))
    return True


def get_definition(accession_list, DEBUG, debug, attempt_no=0):
    """
    Receives a list of gis and returns a list of Entrez records
    :param accession_list:
    :param attempt_no:
    :param DEBUG:
    :param debug:
    :return:
    """
    try:  # fetching from entrez
        handle = Entrez.efetch(db="nucleotide", id=accession_list, retmode="xml")
        records = Entrez.read(handle)
        debug("Successfully connected to Entrez.")
        # get the definition and sequence of each gene
        results = [(res["GBSeq_definition"], res["GBSeq_sequence"]) for res in records]
        return results
    except Exception, e:
        print "Error connecting to server, trying again..."
        print "Error: {}".format(e)
        print "Debug this!"  # todo: connection problem - can we solve it?
        debug("Error connecting to server, trying again...\n")

        # sleeping in case it's a temporary database problem
        sleep_period = 180
        print "restarting attempt in {} seconds...".format(sleep_period)
        sleep(sleep_period)

        # counting the number of attempts to connect.
        attempt_no += 1
        if attempt_no >= 10:  # If too many:
            print "Tried connecting to Entrez DB more than 10 times. Check your connection or try again later."
            exit(1)

        # try again (recursive until max)
        return get_definition(accession_list, DEBUG, debug, attempt_no)  # working on all files together, from all genes


# TODO: doc
def prepare_candidates(file_lines_dict, index_set, enumerator, e_val_thresh, id_thresh, cov_thresh, accession_regex,
                       DEBUG, debug):
    """
    Preparing the candidate genes for retrieval. Returning accession list.
    :param file_lines_dict:
    :param index_set: all remaining indexes for which reciprocal blast hasn't been completed. (list of nums)
    :param enumerator: current line number in each file
    :param e_val_thresh:
    :param id_thresh:
    :param cov_thresh:
    :param accession_regex:
    :param DEBUG:
    :param debug:
    :return:
    """
    debug("line number %s in files:" % enumerator)
    debug("remaining indexes: %s" % index_set)
    remove_me = []
    accessions = []
    index_list = list(index_set)

    for index in index_set:
        # going straight to our desired line according to "enumerator":
        try:
            line_list = split(file_lines_dict[index][enumerator - 1], "\t")
        except IndexError:
            debug("Line {0} does not exist in file {1} does not exist. Moving on to next file!".format(enumerator,
                                                                                                       index))
            remove_me.append(index)  # add the index to remove list
            continue
        identity = float(line_list[2])
        coverage = float(line_list[3])
        evalue = float(line_list[4])
        if evalue < e_val_thresh and identity >= id_thresh and coverage >= cov_thresh:
            try:
                split_line = split(line_list[1], '|')  # still gi. phasing out of it in Sept. 16
                if split_line[2] == 'pdb':
                    accession_v = split_line[1]  # until NCBI phases out of GI, we can't use PDB id so we have to use GI
                else:
                    accession_v = split_line[3]  # if it's the old format: gi|761916618|ref|XP_011407293.1|
            except IndexError:  # if the split didn't work because NCBI changed the format:
                result = re_search(accession_regex, line_list[1])
                accession_v = result.group(1)
            accessions.append(accession_v)

    index_set = set([x for x in index_list if x not in remove_me])

    return accessions, index_set  # a list of accessions/gis


def main(second_blast_folder, e_value_thresh, identity_threshold, coverage_threshold, textual_match,
         textual_sequence_match, species, accession_regex, description_regex, run_folder,
         max_attempts_to_complete_rec_blast, csv_output_filename, fasta_output_folder, DEBUG, debug, id_dic=None,
         second_blast_for_ids_dict=None, gene_paths_list=None):
    """

    :param second_blast_folder:
    :param e_value_thresh:
    :param identity_threshold:
    :param coverage_threshold:
    :param textual_match:
    :param textual_sequence_match:
    :param species:
    :param accession_regex:
    :param description_regex:
    :param run_folder:
    :param max_attempts_to_complete_rec_blast:
    :param csv_output_filename:
    :param fasta_output_folder:
    :param DEBUG:
    :param debug:
    :param id_dic:
    :param second_blast_for_ids_dict:
    :param gene_paths_list:
    :return:
    """
    # deal with args in debug_func mode:
    if DEBUG:
        if not second_blast_for_ids_dict:
            second_blast_for_ids_dict = pickle.load(open(os.path.join(run_folder, "second_blast_for_ids_dict.p"), 'rb'))
        if not id_dic:
            id_dic = pickle.load(open(os.path.join(run_folder, "id_dic.p"), 'rb'))
        if not gene_paths_list:
            # getting the dir paths of each gene
            gene_paths_list = [os.path.join(second_blast_folder, x) for x in os.listdir(second_blast_folder) if
                               os.path.isdir(os.path.join(second_blast_folder, x))]

    # this list contains all genes and their id numbers
    # instead of pickle, getting dict from from the gene_list_to_csv

    all_organisms = []  # initialize organisms list

    # iterating over all gene ids!
    for gene_path_folder in gene_paths_list:
        # extracting the original gene id from the second_blast_folder
        debug("Working on folder: {}".format(gene_path_folder))
        gene_id = int(split(os.path.basename(gene_path_folder), "_")[1])

        this_gene_dic = {}  # the output for each organism in this gene_id

        debug("Working on {}".format(gene_id))  # GENE_ID

        # gene names and description
        target = id_dic[gene_id]
        target_name1 = strip(target[1])  # possible name for gene
        target_name2 = strip(target[2])  # longer possible name for gene
        target_sequence = strip(target[4])
        del target  # don't need it anymore

        debug_file = open(os.path.join(run_folder, "missedhits_for_gene_%s(%s).txt") % (gene_id, target_name1), "w")

        # a list containing all the files we are going to work on, for this gene id:
        all_files_in_gene_id = [file_name for file_name in os.listdir(gene_path_folder) if
                                (os.path.isfile(os.path.join(gene_path_folder, file_name)) and
                                 file_name.endswith('.taxa_filtered.txt'))]

        indexes_per_id = []
        index_files_dict = {}

        # extracting the indexes_per_id from the file names. We are creating a set of all the
        # file indexes_per_id we want to match back to the reference genome
        for index_file_name in all_files_in_gene_id:
            index = int(split(split(index_file_name, "_")[6], '.')[0])  # extracting index
            indexes_per_id.append(index)  # add index
            debug("reading {}".format(os.path.join(gene_path_folder, index_file_name)))
            # now read every max_attempts_to_complete_rec_blast+1 lines of every file and save it in a dictionary,
            # unless the file is shorter and then read all the lines from the file
            with open(os.path.join(gene_path_folder, index_file_name), 'r') as index_infile:
                index_files_dict[index] = list(islice(index_infile, max_attempts_to_complete_rec_blast))

        index_set = set(indexes_per_id)  # converting to set
        debug("indexes per id: {}".format(index_set))  # DEBUG print

        enumerator = 0  # current line number in each index file
        while index_set:
            enumerator += 1
            if enumerator == max_attempts_to_complete_rec_blast:
                # we limit the amount of searches to 100 queries. in each run we throw out the indexes_per_id
                # of the files we managed to match
                break

            # quality check for each line in the files, only those who pass will move on to the next stage
            accessions, index_set = prepare_candidates(index_files_dict, index_set, enumerator, e_value_thresh,
                                                       identity_threshold, coverage_threshold, accession_regex, DEBUG,
                                                       debug)
            debug("accessions: {}".format(accessions))

            # getting taxa info only for the genes that passed the initial quality text
            if accessions:  # if we have any results
                candidates = get_definition(accessions, DEBUG, debug)  # get strings to compare to the original_id

                indexes_to_remove = set()  # set of indexes to remove each round
                index_count = 0
                loci_list = list(index_set)  # the gene position
                debug("loci_list: {}".format(loci_list))

                # string comparison:
                for candidate in candidates:  # for each definition
                    # the current index number of the still unmatched indexes
                    loc = loci_list[index_count]
                    index_count += 1  # increment for next round

                    # cleaning strings before string comparison
                    candidate_name = format_description(candidate[0], description_regex, species)
                    candidate_seq = candidate[1]

                    try:
                        animal_org = second_blast_for_ids_dict[gene_id][int(loc)][1]  # getting from dict of dict
                        fasta_record = second_blast_for_ids_dict[gene_id][int(loc)][0]  # getting from dict of dict
                        is_rbh = second_blast_for_ids_dict[gene_id][int(loc)][2]  # boolean representing RBH
                    except KeyError:  # no value for that id, probably empty
                        debug("No value for index {}".format(loc))
                        continue
                    # if all goes well, we found the animal

                    target_name2 = format_description(target_name2, description_regex, animal_org)

                    # textual matches between the candidate name, description or the sequence itself
                    if similar(upper(candidate_name), upper(target_name1)) > textual_match \
                            or similar(upper(candidate_name), upper(target_name2)) > textual_match \
                            or similar(upper(target_sequence), upper(candidate_seq)) > textual_sequence_match:

                        indexes_to_remove.add(loc)  # in each round, we remove indexes_per_id to which we found a match
                        if update_match_results(enumerator, animal_org, target_name1, this_gene_dic, is_rbh, DEBUG,
                                                debug):
                            debug("Calculated matches for gene_id {0} enumerator {1}".format(gene_id, enumerator))
                        # add the fasta sequence to this fasta output (declared in part 1)
                        fasta_output_file_name = os.path.join(fasta_output_folder,
                                                              "fasta-{0}-{1}.fasta".format(gene_id, target_name1))
                        with open(fasta_output_file_name, 'a') as fasta_output_file:
                            fasta_output_file.write("{}\n\n".format(fasta_record))
                        debug("Added fasta seq to fasta file {}".format(fasta_output_file_name))

                    else:  # couldn't find similarity
                        debug("not similar: %s == %s, %s" % (candidate, target_name2, animal_org))
                        debug_file.write("%s not similar: %s == %s, %s\n" % (candidate_name, target_name1, target_name2,
                                                                             animal_org))

                # preparing new index_set, while in loop
                # removing indexes_per_id for which a match has been found
                index_set = index_set - indexes_to_remove

                # debug_func print:
                debug("List of indexes to remove:\n{0}\nSet of indexes left for next round:{1}".format(
                    indexes_to_remove, index_set))

        # documenting full reciprocal blast results for this gene
        pickle.dump(this_gene_dic, open(os.path.join(run_folder, 'full_results_for_ID_%s-%s.p' %
                                                     (gene_id, target_name1)), 'wb'))

        # add this_gene_dic to a final result dic
        all_genes_dict[target_name1] = this_gene_dic
        all_organisms += [x for x in this_gene_dic.keys()]  # a list of the organisms with results

    # writing final csv output:
    if write_all_output_csv(all_genes_dict, all_organisms, csv_output_filename, DEBUG, debug):
        print "Wrote csv output to file: {}".format(csv_output_filename)
    print("Printed all the output fasta sequences to folder {}".format(fasta_output_folder))

    print "done!"
    return True

