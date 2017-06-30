'use strict'

angular.module('upmark.utils.watch', [
    'upmark.utils.logging'])


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


;
