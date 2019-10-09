'use strict'

angular.module('vpac.widgets.text', [])


/**
 * Specialisation of angular-list-match-patch for lists of numbers.
 */
.directive('pathDiff', function() {
    return {
        restrict: 'AC',
        scope: {
            left: '=leftObj',
            right: '=rightObj'
        },
        link: function(scope, elem, attrs) {
            var sanitise = function(text) {
                var pattern_amp = /&/g;
                var pattern_lt = /</g;
                var pattern_gt = />/g;
                return text.replace(pattern_amp, '&amp;')
                        .replace(pattern_lt, '&lt;')
                        .replace(pattern_gt, '&gt;');
            };

            var createHtml = function(left, right) {
                if (!angular.isString(left))
                    left = '';
                if (!angular.isString(right))
                    right = '';
                var left = sanitise(left);
                var right = sanitise(right);

                var leftArr = left.split('.');
                var rightArr = right.split('.');
                var nitems = Math.max(leftArr.length, rightArr.length);
                var html = '';
                for (var i = 0; i < nitems; i++) {
                    var leftComponent = leftArr[i];
                    var rightComponent = rightArr[i];
                    var pad = i > 0 ? ' ' : '';
                    if (!leftComponent && !rightComponent) {
                        // Skip empty path element.
                    } else if (!leftComponent) {
                        html += '<ins>' + pad + rightComponent + '.</ins>';
                    } else if (!rightComponent) {
                        html += '<del>' + pad + leftComponent + '.</del>';
                    } else if (leftComponent != rightComponent) {
                        html += '<del>' + pad + leftComponent + '.</del>';
                        html += '<ins>' + pad + rightComponent + '.</ins>';
                    } else {
                        html += pad + rightComponent + '.';
                    }
                }
                return html;
            };

            var listener = function(vals) {
                elem.html(createHtml(vals[0], vals[1]));
            };

            scope.$watchGroup(['left', 'right'], listener);
        }
    };
})
