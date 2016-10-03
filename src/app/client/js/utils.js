'use strict';

angular.module('vpac.utils', [])

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

.factory('paged', [function() {
    return function(response) {
        var data = response.resource;
        data.$pageIndex = parseInt(response.headers('Page-Index'));
        data.$pageItemCount = parseInt(response.headers('Page-Item-Count'));
        data.$pageCount = parseInt(response.headers('Page-Count'));
        return data;
    };
}])

/*
 * Simple string interpolation. E.g.
 *
 * format('foo {} {} {}', 'a', 'b', 'c');
 * "foo a b c"
 *
 * format('foo {2} {1} {0}', 'a', 'b', 'c');
 * "foo c b a"
 *
 * format('foo {2} {1} {0}', ['a', 'b', 'c']);
 * "foo c b a"
 *
 * format('foo {bar} {baz}', {bar: "a", baz: "b"});
 * "foo a b"
 */
.factory('format', ['$filter', function($filter) {
    var re = /(^|[^\\]){([^{}]*)}/g;
    var json = $filter('json');

    return function write(format, args) {
        var autoIndex = 0;
        var offset = 0;
        if (!angular.isObject(args) && !angular.isArray(args)) {
            args = arguments;
            offset = 1;
        }
        var message = format.replace(re, function(match, prefix, key) {
            if (key == "")
                key = autoIndex++;
            var ordinal = Number(key);
            if (!isNaN(ordinal))
                key = ordinal + offset;
            var value = args[key];
            if (value === undefined)
                return match;
            else if (angular.isObject(value))
                return json(value);
            else
                return prefix + value;
        });
        return message;
    };
}])

/*
 * Simple logging with string interpolation. E.g.
 *
 * log.info('foo {} {} {}', 'a', 'b', 'c');
 * "foo a b c"
 *
 * Logging levels can be configured by using logProvider in your app config:
 *
 * module.config(function(logProvider) {
 *     logProvider.levels.debug = true;
 * };
 */
.provider('log', ['$logProvider', function logProvider($logProvider) {

    $logProvider.debugEnabled(true);
    var orderedLevels = ['log', 'error', 'warn', 'info', 'debug'];

    var levels = this.levels = {};

    this.setLevel = function(level) {
        var index = orderedLevels.indexOf(level);
        for (var i = 0; i < orderedLevels.length; i++) {
            var name = orderedLevels[i];
            this.levels[name] = i <= index;
        }
    };

    this.setLevel('info');

    this.$get = ['$log', 'format', function($log, format) {
        this.logger = function(level) {
            if (!levels[level])
                return function noop() {};

            var writer = $log[level];

            return function write(formatSpec, args) {
                var message = format.apply(undefined, arguments);
                writer(message);
            };
        };

        return {
            log: this.logger('log'),
            info: this.logger('info'),
            warn: this.logger('warn'),
            error: this.logger('error'),
            debug: this.logger('debug'),
            off: function noop() {}
        };
    }];
}])

/*
 * Easy single-value binding.
 */
.factory('bind', ['$parse', 'log', function($parse, log) {
    return function(scope1, path1, scope2, path2, twoWay, logLevel) {
        var get1 = $parse(path1);
        var get2 = $parse(path2);
        var logger = log[logLevel] || log.debug;

        if (!path1 || !path2)
            throw "Missing path; can't bind.";

        logger('bind: Binding {}.{} to {}.{}',
            scope2.$id, path2, scope1.$id, path1);

        scope1.$watch(path1, function(value) {
            if (value === undefined)
                return;
            logger('bind: {}.{} = {}.{} = {}',
                scope2.$id, path2, scope1.$id, path1, value);
            get2.assign(scope2, value);
        });

        if (twoWay) {
            logger('bind: Binding {}.{} to {}.{}',
                scope1.$id, path1, scope2.$id, path2);

            scope2.$watch(path2, function(value) {
                if (value === undefined)
                    return;
                logger('bind: {}.{} = {}.{} = {}',
                    scope1.$id, path1, scope2.$id, path2, value);
                get1.assign(scope1, value);
            });
        }
    };
}])

/*
 * Watch a property of every item in an array.
 * @param scope The scope that owns the array.
 * @param collectionExpression The collection to watch.
 * @param memberExpression The property to watch, of each item.
 * @param collectionCallback A function to run when the collection changes.
 *      Arguments: newCollection, oldCollection.
 * @param memberCallback A function to run when the property of an item
 *      changes. Arguments: newValue, oldValue, item.
 */
.factory('WatchMany', [function() {

    var cbFactory = function(item, callback) {
        var cb = function(newValue, oldValue) {
            return callback(newValue, oldValue, cb.item);
        };
        cb.item = item;
        return cb;
    };

    var destroyCallback = function(cb) {
        cb.item = null;
        cb.watcher();
        cb.watcher = null;
    };

    return function(scope, collectionExpression, memberExpression,
            collectionCallback, memberCallback) {
        var callbacks = null;

        var deregisterWatch = function() {
            if (!callbacks)
                return;
            for (var i = 0; i < callbacks.length; i++)
                destroyCallback(callbacks[i]);
            callbacks = null;
        };

        scope.$watch(collectionExpression, function(collection, oldCollection) {
            if (collectionCallback)
                collectionCallback(collection, oldCollection);

            // Deregister old watchers.
            deregisterWatch();

            if (!collection || !collection.length)
                return;

            // Register new watchers.
            callbacks = [];
            for (var i = 0; i < collection.length; i++) {
                var exp = collectionExpression + '[' + i + '].'
                        + memberExpression;
                var callback = cbFactory(collection[i], memberCallback);
                callback.watcher = scope.$watch(exp, callback);
                callbacks.push(callback);
            }
        });

        scope.$on('$destroy', function() {
            deregisterWatch();
        });

        return deregisterWatch;
    };
}])


/*
 * Queues a function to be called once asynchronously. After being called, it
 * can be queued again.
 * @param callback The function to call.
 * @param delay The amount of time to wait before calling (defaults to 0).
 * @return A function that will queue up an execution of the callback. It may
 * be called with an argument, but only the most recent value will be passed to
 * the callbacks. To cancel the execution, pass the function to
 * Enqueue.cancel(). If the function is called as a method, the object is made
 * available to the callbacks via the this keyword.
 */
.factory('Enqueue', ['$timeout', function($timeout) {
    var Enqueue = function(callback, delay) {
        var enqueue = function() {
            enqueue.args = arguments;
            enqueue.that = this;
            if (enqueue.promise)
                $timeout.cancel(enqueue.promise);
            else if (enqueue.start)
                enqueue.start.apply(enqueue.that, enqueue.args);
            if (enqueue.always)
                enqueue.always.apply(enqueue.that, enqueue.args);
            enqueue.promise = $timeout(function enqueueCb() {
                try {
                    callback.apply(enqueue.that, enqueue.args);
                } finally {
                    try {
                        if (enqueue.end)
                            enqueue.end(enqueue.that, enqueue.args);
                    } finally {
                        enqueue.that = undefined;
                        enqueue.promise = null;
                        enqueue.args = undefined;
                    }
                }
            }, enqueue.delay);
        };
        enqueue.promise = null;
        enqueue.that = undefined;
        enqueue.args = undefined;
        enqueue.end = null;
        enqueue.start = null;
        enqueue.always = null;
        enqueue.delay = delay;
        return enqueue;
    };
    Enqueue.cancel = function(enqueue) {
        $timeout.cancel(enqueue.promise);
        enqueue.promise = null;
        enqueue.that = undefined;
        enqueue.args = undefined;
    };
    return Enqueue;
}])


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

.factory('Numbers', [function() {
    var Numbers = {
        /**
         * Find the modulo of two numbers, using floored division.
         * http://stackoverflow.com/a/3417242/320036
         * http://en.wikipedia.org/wiki/Modulo_operation
         */
        mod: function(dividend, divisor) {
            return ((dividend % divisor) + divisor) % divisor;
        },
        /**
         * Linear interpolation between two values, e.g. lerp(1, 3, 0.5) == 2
         */
        lerp: function(a, b, fraction) {
            return ((b - a) * fraction) + a;
        },
        /**
         * Inverse linear interpolation between two values. Formally:
         *
         *    lerp(a, b, unlerp(a, b, x)) == x
         *
         * e.g. unlerp(1, 3, 2) == 0.5
         *
         * If a == b, the result is always 0.
         */
        unlerp: function(a, b, value) {
            var divisor = b - a;
            if (divisor == 0)
                return 0;
            return (value - a) / divisor;
        },
        /**
         * Stable function to transform an integer into a seemingly random
         * real number between 0.0 and 1.0.
         */
        hash: function(x) {
            // Robert Jenkins' 32 bit integer hash function.
            // http://stackoverflow.com/a/3428186/320036
            // The prime given on the first line happens to give a good result
            // for boolean datasets.
            var seed = x ^ 1376312589;
            seed = ((seed + 0x7ed55d16) + (seed << 12))  & 0xffffffff;
            seed = ((seed ^ 0xc761c23c) ^ (seed >>> 19)) & 0xffffffff;
            seed = ((seed + 0x165667b1) + (seed << 5))   & 0xffffffff;
            seed = ((seed + 0xd3a2646c) ^ (seed << 9))   & 0xffffffff;
            seed = ((seed + 0xfd7046c5) + (seed << 3))   & 0xffffffff;
            seed = ((seed ^ 0xb55a4f09) ^ (seed >>> 16)) & 0xffffffff;
            return (seed & 0xfffffff) / 0x10000000;
        },
        /**
         * Convert an integer to a character ID - e.g. 0 -> a, 1 -> b, 25 -> z,
         * 26 -> aa, 27 -> ab, etc.
         */
        idOf: function(i) {
            return (i >= 26 ? Numbers.idOf((i / 26 >> 0) - 1) : '') +
                'abcdefghijklmnopqrstuvwxyz'[i % 26 >> 0];
        }
    };
    return Numbers;
}])

.factory('Strings', [function() {
    return {
        /**
         * Generate an integer hash code from a string.
         */
        hashCode: function(str) {
            // http://www.cse.yorku.ca/~oz/hash.html
            // http://stackoverflow.com/a/7616484/320036
            var hash = 0;
            for (i = 0; i < this.length; ++i) {
                var chr = str.charCodeAt(i);
                hash = ((hash << 5) - hash) + chr;
                hash = hash & hash;
            }
            return hash;
        }
    };
}])


/**
 * Factory for convenience methods for the observer pattern.
 *
 * Usage:
 *     # Create the helper:
 *     $on = Observable();
 *     # Register a listener:
 *     $on('fooEvent', function(data) {
 *         console.log(data);
 *     });
 *     # Fire an event:
 *     $on.fire('fooEvent', 'bar');
 *     # Prints 'bar' to the console.
 */
.factory('Observable', [function() {
    return function() {
        var Observable = function(name, listener) {
            var listeners = Observable.listeners[name];
            if (!listeners) {
                listeners = [];
                Observable.listeners[name] = listeners;
            }
            listeners.push(listener);
            return function() {
                var index = listeners.indexOf(listener);
                if (index >= 0)
                    listeners.splice(index, 1);
            }
        };

        Observable.listeners = {};

        Observable.fire = function(name, data) {
            var listeners = Observable.listeners[name];
            if (!listeners)
                return;
            for (var i = 0; i < listeners.length; i++)
                listeners[i].call(null, data);
        };

        return Observable;
    };
}])


/*
 * Maintains a selection of objects, with one object as the "active" (focused)
 * member.
 */
.factory('WorkingSet', ['Arrays', 'Observable', function(Arrays, Observable) {
    function WorkingSet(primaryKey) {
        this.key = primaryKey;
        this.members = [];
        this.active = null;
        this.lastActive = null;
        this.$on = Observable();
    };
    WorkingSet.prototype.index = function(memberOrId) {
        var criterion = {};
        criterion[this.key] = memberOrId[this.key] || memberOrId;
        return Arrays.indexOf(this.members, criterion, this.key);
    };
    WorkingSet.prototype.get = function(memberOrId) {
        var index = this.index(memberOrId);
        if (index < 0)
            return null;
        return this.members[index];
    };
    WorkingSet.prototype.add = function(member) {
        var index = this.index(member);
        if (index >= 0)
            return;
        this.members.push(member);
        this.$on.fire('add', member);
    };
    WorkingSet.prototype.remove = function(member) {
        var index = this.index(member);
        if (index < 0)
            return;

        this.members.splice(index, 1);

        if (this.members.length > 0) {
            if (index == this.members.length)
                index--;
            this.activate(this.members[index]);
        } else {
            this.lastActive = null;
            this.activate(null);
        }
        this.$on.fire('remove', member);
    };
    WorkingSet.prototype.activate = function(member) {
        if (member != null) {
            this.add(member);
            this.lastActive = member;
        }
        this.active = member;
        this.$on.fire('activate', member);
    };

    return function(key) {
        return new WorkingSet(key);
    };
}])


/**
 * Focus an element in response to an event.
 */
.directive('focusOn', [function() {
    return {
        restrict: 'A',
        link: function(scope, element, attrs) {
            var remove = null;
            scope.$watch(attrs.focusOn, function(focusOn) {
                if (remove)
                    remove();
                remove = scope.$on(focusOn, function(event) {
                    console.log('focusOn', event)
                    element.focus();
                });
            });
            scope.$on('$destroy', function() {
                element = null;
                remove = null;
            });
        }
    }
}])


/**
 * Return focus to the last-focussed element in response to an event.
 */
.directive('blurOn', ['$window', '$document', function($window, $document) {
    return {
        restrict: 'A',
        link: function(scope, element, attrs) {
            var lastFocussedElement = null;

            var globalFocusHandler = function(event) {
                var target = angular.element(event.target);
                if (target.prop('tagName') === undefined) {
                    // Don't store window; it may be only temporarily focussed
                    // when the user switches back to the window.
                } else if (!element.is(target)) {
                    lastFocussedElement = target;
                }
            };
            angular.element($window).on('focusin', globalFocusHandler);

            var remove = null;
            scope.$watch(attrs.blurOn, function(blurOn) {
                if (remove)
                    remove();
                remove = scope.$on(blurOn, function(event) {
                    console.log('blurOn', event)
                    if (!element.is(':focus'))
                        return;

                    var lastElem = lastFocussedElement;
                    lastFocussedElement = null;

                    // Transfer focus to last selected element, or fall back to
                    // window if lastElem can't be focussed.
                    if (lastElem && $.contains($document[0].documentElement,
                                               lastElem[0]))
                        lastElem.focus();
                    else
                        element.blur();
                });
            });

            scope.$on('$destroy', function() {
                lastFocussedElement = null;
                scope = null;
                element = null;
                attrs = null;
                remove = null;
                angular.element($window).off('focusin', globalFocusHandler);
            });
        }
    }
}])


.factory('tricycle', [function() {
    return function(value) {
        // null -> false -> true -> null etc.
        if (value == null)
            return false;
        else if (value)
            return null;
        else
            return true;
    };
}])


;
