'use strict'

angular.module('upmark.utils.arrays', [])


.factory('Arrays', [function() {
    return {
        /**
         * Search for an item in an array, using a customisable access function.
         * @param arr the array to search through.
         * @param item the item to find in the array
         * @param getter an access function or string.
         *  - If it's a function, then it is used to transform the items that
         *    are being inspected as in getter(arr[i]) == getter(item).
         *  - If it's a string, then fields of that name are used for comparison
         *    as in arr[i][getter] == item[getter].
         *  - If it's undefined, then the items themselves are compared as in
         *    arr[i] == item.
         * @return the index of the item or -1 if it was not found.
         */
        indexOf: function(arr, item, getter, iGetter) {
            function makeGetter(getter) {
                var fn;
                if (angular.isFunction(getter))
                    fn = function(x) { return fn.getter(x); };
                else if (angular.isString(getter))
                    fn = function(x) { return x[fn.getter]; };
                else
                    fn = function(x) { return x; };
                fn.getter = getter;
                return fn;
            };

            var get, iGet = get = {};

            try {
                get = makeGetter(getter);
                if (iGetter === undefined)
                    iGet = get;
                else
                    iGet = makeGetter(iGetter);

                var keyNeedle = iGet(item);

                if (angular.isFunction(getter)) {
                    for (var i = 0; i < arr.length; i++) {
                        var keyHaystack = getter(arr[i]);
                        if (keyHaystack == keyNeedle)
                            return i;
                    }
                } else if (angular.isString(getter)) {
                    for (var i = 0; i < arr.length; i++) {
                        var keyHaystack = arr[i][getter];
                        if (keyHaystack == keyNeedle)
                            return i;
                    }
                } else {
                    for (var i = 0; i < arr.length; i++) {
                        var keyHaystack = arr[i];
                        if (keyHaystack == keyNeedle)
                            return i;
                    }
                }
                return -1;
            } finally {
                get.getter = null;
                iGet.getter = null;
            }
        },

        /**
         * Search a sorted array for an item, using a customisable access
         * function. If the item doesn't exist in the array, the insertion point
         * is returned instead.
         * @param arr the array to search through.
         * @param item the item to find in the array
         * @param getter an access function or string. See indexOf for details.
         * @return the index of the item, or (-insertionPoint - 1). See
         * http://docs.oracle.com/javase/7/docs/api/java/util/Arrays.html#binarySearch(int[],%20int)
         */
        search: function(arr, item, getter) {
            var insertionPoint = 0;
            if (angular.isFunction(getter)) {
                var keyNeedle = getter(item);
                for (var i = 0; i < arr.length; i++) {
                    var keyHaystack = getter(arr[i]);
                    if (keyHaystack == keyNeedle)
                        return i;
                    else if (keyHaystack < keyNeedle)
                        insertionPoint = i + 1;
                    else
                        break;
                }
            } else if (angular.isString(getter)) {
                var keyNeedle = item[getter];
                for (var i = 0; i < arr.length; i++) {
                    var keyHaystack = arr[i][getter];
                    if (keyHaystack == keyNeedle)
                        return i;
                    else if (keyHaystack < keyNeedle)
                        insertionPoint = i + 1;
                    else
                        break;
                }
            } else {
                var keyNeedle = item;
                for (var i = 0; i < arr.length; i++) {
                    var keyHaystack = arr[i];
                    if (keyHaystack == keyNeedle)
                        return i;
                    else if (keyHaystack < keyNeedle)
                        insertionPoint = i + 1;
                    else
                        break;
                }
            }
            return -insertionPoint - 1;
        }
    }
}])


;
