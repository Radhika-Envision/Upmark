'use strict'

angular.module('vpac.utils.queue', [])


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
    var Enqueue = function Enqueue(callback, delay, scope) {
        var enqueue = function() {
            if (enqueue.destroyed)
                return;
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
        enqueue.destroyed = false;
        enqueue.promise = null;
        enqueue.that = undefined;
        enqueue.args = undefined;
        enqueue.end = null;
        enqueue.start = null;
        enqueue.always = null;
        enqueue.delay = delay;
        if (scope) {
            scope.$on('$destroy', function() {
                Enqueue.destroy(enqueue);
            });
        }
        return enqueue;
    };
    Enqueue.cancel = function(enqueue) {
        $timeout.cancel(enqueue.promise);
        enqueue.promise = null;
        enqueue.that = undefined;
        enqueue.args = undefined;
    };
    Enqueue.destroy = function(enqueue) {
        enqueue.destroyed = true;
        Enqueue.cancel(enqueue);
    };
    return Enqueue;
}])


;
