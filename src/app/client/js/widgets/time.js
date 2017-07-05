'use strict'

angular.module('vpac.widgets.time', [])


.directive('secondsAsDays', function() {
    return {
        restrict: 'A',
        require: 'ngModel',
        link: function (scope, elem, attrs, ngModel) {
            ngModel.$parsers.push(function(value) {
                return value * (60 * 60 * 24);
            });
            ngModel.$formatters.push(function(value) {
                return value / (60 * 60 * 24);
            });
        }
    };
})


.directive('printFriendlyTimeago', function() {
    return {
        restrict: 'A',
        scope: {
            date: '=printFriendlyTimeago',
            format: '@?pfFormat',
            titleFormat: '@?pfTitleFormat',
            units: '@?pfUnits',
        },
        template: '<span class="hidden-print" '+
                        'title="{{date * multiplier | date:titleFormat}}">' +
                    '{{date * multiplier | timeAgo:format}}</span>' +
                  '<span class="visible-print-inline">' +
                    '{{date * multiplier | date:format}}</span>',
        link: function (scope, elem, attrs) {
            if (!scope.format)
                scope.format = 'mediumDate';
            if (!scope.titleFormat)
                scope.titleFormat = 'medium';
            if (!scope.units)
                scope.units = 'ms';
            scope.multiplier = 1.0;
            scope.$watch('units', function(units) {
                scope.multiplier = {
                    s: 1,
                    ms: 1000,
                    us: 1000000,
                    μs: 1000000,
                }[units];
            });
        }
    };
})


;
