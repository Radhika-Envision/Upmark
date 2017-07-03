'use strict'

angular.module('vpac.widgets.spinner', [])


.directive('spinner', ['Enqueue',
        function(Enqueue) {
    var pendingRequests = 0;
    var patchOpen = function() {
        var oldOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url, async, user, pass) {
            pendingRequests++;
            this.addEventListener("readystatechange", function() {
                if (this.readyState == 4)
                    pendingRequests--;
            }, false);
            oldOpen.call(this, method, url, async, user, pass);
        };
    };
    patchOpen();

    return {
        restrict: 'C',
        link: function(scope, elem, attrs, form) {
            var show = Enqueue(function() {
                elem.toggleClass('in', true);
            }, 250, scope);
            var hide = function() {
                Enqueue.cancel(show);
                elem.toggleClass('in', false);
            };
            scope.$watch(
                function() {
                    return pendingRequests > 0;
                },
                function(pending) {
                    if (pending)
                        show();
                    else
                        hide();
                }
            );
        }
    };
}])


;
