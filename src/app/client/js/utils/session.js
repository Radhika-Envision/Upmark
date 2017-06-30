'use strict'

angular.module('upmark.utils.session', [])


/*
 * Generates ids unique to this session.
 */
.factory('guid', [function() {
    var seq = 0;
    return function(prefix) {
        var id = seq.toString(36);
        seq++;
        if (prefix != undefined)
            return prefix + '_' + id;
        else
            return id;
    };
}])


;
