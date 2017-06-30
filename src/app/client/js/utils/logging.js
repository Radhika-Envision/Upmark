'use strict'

angular.module('upmark.utils.logging', [])


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


;
