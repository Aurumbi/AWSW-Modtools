from algorithms.jaro_batched import build_word_letter_lookup, jaro_using_wl_lookup, MAX_WORD_SIZE


def _get_words(string):
    return set(string.lower().split())


class BatchedJaroSearchManager:
    def __init__(self, modlist):
        self._modlist = modlist
        self._mods_by_id = {mod.id: mod for mod in self._modlist}
        
        word_list = set()
        for mod in modlist:
            word_list.update(_get_words(mod.name) | _get_words(mod.desc))
        
        # Note the difference in handling long words vs long author names now that there's a limit.
        # Long words are not really supposed to be searched as the main searchbox is quite small and generally uses multiple,
        #   so they can safely be ignored.
        # Author names may be of any length and need to be searchable. Additionally you generally only search for one at a time.
        #   therefore we decide to truncate them, so that they'll still be easy to search.
        self._word_list = {word for word in word_list if len(word) <= MAX_WORD_SIZE}
        self._author_list = {mod.author[:MAX_WORD_SIZE] for mod in modlist}
        self._wl_lookup = build_word_letter_lookup(words=self._word_list)
        self._author_wl_lookup = build_word_letter_lookup(words=self._author_list)
    
    
    def sort_best(self, query, author_query="", return_score=False):
        """ Sort mods by best match to query.
        Ensure that the parameter word_list to this classes' __init__ contains all words """
        query_words = {word for word in _get_words(query) if len(word) <= MAX_WORD_SIZE}
        author_query = author_query.strip()[:MAX_WORD_SIZE]
        
        per_word_scores = {word: jaro_using_wl_lookup(query=word, words=self._word_list, wl_lookup=self._wl_lookup) for word in query_words}
        
        per_author_scores = jaro_using_wl_lookup(query=author_query, words=self._author_list, wl_lookup=self._author_wl_lookup)
        
        query_scores = {}
        author_scores = {}
        for mod in self._modlist:
            if query_words:
                name_words = _get_words(mod.name)
                desc_words = _get_words(mod.desc)
                name_similarity = 0
                desc_similarity = 0
                
                for query_word in query_words:
                    name_similarity += max(per_word_scores[query_word].get(test_word) for test_word in name_words)
                    desc_similarity += max(per_word_scores[query_word].get(test_word) for test_word in desc_words)
                
                name_similarity /= len(query_words)
                desc_similarity /= len(query_words)
                
                query_scores[mod.id] = (name_similarity, desc_similarity)
            else:
                query_scores[mod.id] = (0.0, 0.0)
            
            if author_query:
                author_scores[mod.id] = per_author_scores[mod.author]
            else:
                author_scores[mod.id] = 0.0
        
        similarities = {mod_id: scores + (author_scores[mod_id],) for mod_id, scores in query_scores.iteritems()}  # Much easier to deal with if it's a single iterable
        # Sort by best match, with bias to strong modname matches and strong authorname matches
        #  This bias is useful as the description normally takes the stronger value, unless the mod name is searched specifically.
        #  Max gave me better results than sum, so I used it.
        comp_func = lambda e: (max(e[1][:2]) + (int(e[1][0] > 0.9) * e[1][0]) + (int(e[1][2] > 0.7) * e[1][2]))
        mod_order = list(sorted(similarities.items(), key=comp_func, reverse=True))
        
        if comp_func(mod_order[0]) <= 0.3:  # All bad matches, don't reorder
            print "No good matches. reordering suppressed"
            mod_order = list((mod.id, 0.0) for mod in self._modlist)
        
        if return_score:
            return [(self._mods_by_id[mod_id], score) for mod_id, score in mod_order]
        else:
            return [self._mods_by_id[mod_id] for mod_id, _ in mod_order]