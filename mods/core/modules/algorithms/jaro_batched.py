""" Implements a quick implementation of jaro similarity against a constant word list.
This uses a precomputed mapping from letters to words that contain that letter (build_word_letter_lookup),
along with a bitwise representation of letter presence/absence in each word position, which allows finding letter matches using bitwise operations.

Usage:
1. build a letter lookup table by calling build_word_letter_lookup. you should do so with the full list of words, and only do so once for each wordlist.
2. call jaro_complex on your queries using the precomputed result of build_word_letter_lookup.

Usage is most efficient if build_word_letter_lookup is called once, then used for many calls to jaro_complex.

This is a modified version of the code at the core of the pseudo jaro winkler repo (<https://github.com/ipums/pseudo_jaro_winkler>),
Translated into python and further modified to suit our needs.
As such it is under the terms of their license, available both as a local copy here (./PJW_LICENSE.txt) and at their source (<https://github.com/ipums/pseudo_jaro_winkler/blob/main/LICENSE.txt>).
See ./PJW_LICENSE.txt for the licensing information, along with ./PJW_NOTICE.txt for their notice information.
"""


def _build_query_masks(query):
    """ Create list of (letter, mask_list) pairs for each character in query.
    mask_list is a list of length 31,
     where each mask is all positions that jaro logic can match the current letter to it given the candidate is of length i+1.
    example, for mask list size 5 (as I can't practically do size 31):
      "aba" -> [("a", [0b00001, 0b00001, 0b00001, 0b00011, 0b00011,]),
                ("b", [0b00010, 0b00010, 0b00010, 0b00111, 0b00111,]),
                ("a", [0b00100, 0b00100, 0b00100, 0b01110, 0b01110,]),]
    """
    result = []
    
    for letter in query:
        result.append((letter, []))
    
    min_shift_dist = max(int(len(query) / 2), 1) - 1
    for cand_size in range(1, 32):
        shift_dist = max(int(cand_size / 2) - 1, min_shift_dist)
        
        # Create symmetric block of ones, centered at bit 15, extending shift_dist bits in each direction
        # Bit 15 is chosen as we decided (relatedly) to limit words to 31 characters,
        #  and under that choice bit 15 is the centermost bit of the 31 bit mask.
        # 31 characters have been chosen as it fits in a 32 bit integer and is odd.
        # oddness is required for there to be a center bit, as we rely on one here.
        base_bitmask = ((0x1 << (2 * shift_dist + 1)) - 1) << (15 - shift_dist)
        
        for letter_pos, letter in enumerate(query):
            if letter_pos < 15:
                bitmask = base_bitmask >> (15 - letter_pos)
            else:
                # First cutoff then shift to ensure everything stays within 31 bits
                bitmask = (0x7FFFFFFF >> (letter_pos - 15)) & base_bitmask
                bitmask = bitmask << (letter_pos - 15)
            
            result[letter_pos][1].append(bitmask)
    
    return result


def _count_trailing_zeroes(n):
    return max((n & -n).bit_length(), 1) - 1


def _update_score_on_next_masks(candidate_scorer, query_mask, candidate_mask):
    """ Update scorer candidate_scorer using the masks as the next letter to check.
    This should be used in a loop over the query's letters in order, where each letter has the appropriate expanded mask.
    :param candidate_scorer: mapping score card to be updated, containing:
        'matches': # of matches found,
        'transpositions': # of swaps found,
        'used': bitmask of character positions already matched in the candidate.
    :param query_mask: expanded mask, as returned from _build_query_masks, matching the length of the candidate.
    :param candidate_mask: mask containing 1 for each position in candidate containing the current checked character.
    """
    whole_mask_result = query_mask & candidate_mask  # Get raw matches
    check_used_result = whole_mask_result & ~candidate_scorer["used"]  # Make sure we haven't used that match before
    mask_result = (0x1 << _count_trailing_zeroes(
        check_used_result)) & check_used_result  # Checking one char at a time, so prefer first match
    is_match = int(mask_result != 0)
    candidate_scorer["matches"] += is_match
    candidate_scorer["transpositions"] += mask_result and (mask_result - 1 < candidate_scorer["used"])
    candidate_scorer["used"] |= mask_result
    return


def build_word_letter_lookup(words):
    """ Create {letter: list[(word, mask)]} structure for quick lookup of words which contain a letter, for each letter in the words of words.
    The keys are all letters contained in at least one word of words.
    each value is a list, containing all words in words which contain the key, along with bitmaps of in which position in the word the key appears.
    This allows for quick and efficient testing for matching using bitwise operations.
    """
    result = {}
    all_letters = {letter for word in words for letter in word}
    for letter in all_letters:
        next_v = {}
        for word in words:
            next_mask = 0
            for i in (i for i, l in enumerate(word) if l == letter):
                next_mask |= 0x1 << i
            
            if next_mask:
                next_v[word] = {"len": len(word), "mask": next_mask}
        
        result[letter] = next_v
    
    return result


def calculate_jaro_score(matches, transpositions, length_1, length_2):
    if not matches: return 0.0
    
    # I'm honestly not sure why the possible -1 is there.
    # it is inherited from the calculate_jaro_winkler from the pseudo jaro winkler repo, and I didn't want to remove it if I don't understand it.
    # It seems to work, though!
    transpositions = transpositions - int(transpositions > matches / 2)
    return ((float(matches) / length_1) + (float(matches) / length_2) + 1.0 - (transpositions / float(matches))) / 3.0


def jaro_using_wl_lookup(query, words, wl_lookup):
    """ Calculate jaro similarity for query against all words in words, using precomputed build_word_letter_lookup result."""
    query_masks = _build_query_masks(query)
    
    inter_scores = {word: {"matches": 0, "transpositions": 0, "used": 0x0} for word in words}
    for curr_letter, curr_letter_masks in query_masks:
        if curr_letter not in wl_lookup:
            continue
        applicable_words = wl_lookup[curr_letter]
        for word, curr_word_info in applicable_words.iteritems():
            curr_query_mask = curr_letter_masks[curr_word_info["len"] - 1]
            _update_score_on_next_masks(inter_scores[word], curr_query_mask, curr_word_info["mask"])
    
    query_len = len(query)
    return {word: calculate_jaro_score(scorer["matches"], scorer["transpositions"], len(word), query_len)
            for word, scorer in inter_scores.iteritems()}
