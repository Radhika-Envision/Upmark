'use strict';

angular.module('wsaa.survey', ['ngResource'])


.factory('Schema', ['$resource', function($resource) {
    return $resource('/schema/:name.json', {name: '@name'}, {
        get: { method: 'GET' }
    });
}])


.factory('Measure', ['$resource', function($resource) {
    return $resource('/survey/:survey/function/:fn/process/:proc/sub-process/:subProc/measure/:measure.json', {}, {
        get: { method: 'GET' }
    });
}])


.controller('SurveyCtrl', ['$scope', '$routeParams', 'Schema', 'Measure', 'format',
        function($scope, $routeParams, Schema, Measure, format) {

    $scope.route = {
        params: $routeParams,
        nextUrl: null,
        prevUrl: null
    };
    $scope.measure = Measure.get($routeParams);
    $scope.schema = null;
    $scope.response = {
        na: false,
        comment: ""
    };

    $scope.$watch('measure.responseType', function(responseType) {
        if (responseType == null)
            return;
        $scope.schema = Schema.get({name: responseType});
    });

    $scope.$watchGroup(['route.params', 'measure.first'], function(vars) {
        var params = vars[0];
        var end = vars[1];
        if (end) {
            $scope.route.prevUrl = null;
            return;
        }

        $scope.route.prevUrl = format(
            "#/survey/{}/{}/{}/{}/{}",
            $scope.route.params.survey,
            $scope.route.params.fn,
            $scope.route.params.proc,
            $scope.route.params.subProc,
            Number($scope.route.params.measure) - 1
        );
    });

    $scope.$watchGroup(['route.params', 'measure.last'], function(vars) {
        var params = vars[0];
        var end = vars[1];
        if (end) {
            $scope.route.nextUrl = null;
            return;
        }

        $scope.route.nextUrl = format(
            "#/survey/{}/{}/{}/{}/{}",
            $scope.route.params.survey,
            $scope.route.params.fn,
            $scope.route.params.proc,
            $scope.route.params.subProc,
            Number($scope.route.params.measure) + 1
        );
    });

}])


.controller('ResponseStandardCtrl', ['$scope', 'hotkeys', ResponseStandardCtrl])

;


function BaseResponseCtrl($scope) {
};

function ResponseStandardCtrl($scope, hotkeys) {
    BaseResponseCtrl.call(this, $scope);

    $scope.$watch('schema', function(schema) {
        $scope.response.active = 0;
        $scope.response.responses = [];
        for (var i = 0; i < schema.responses.length; i++) {
            $scope.response.responses[i] = -1;
        }
    });

    $scope.respond = function(response, choice) {
        var i = $scope.schema.responses.indexOf(response);
        var j = response.choices.indexOf(choice);
        $scope.response.responses[i] = j;
        $scope.response.active = i + 1;
    };

    $scope.disabled = function(i, j) {
        if ($scope.response.na)
            return true;

        if (i == 0)
            return false;

        var prevResp = $scope.response.responses[i - 1];
        if (j == undefined)
            return prevResp < 0;

        var currDecl = $scope.schema.responses[i].choices[j];
        if (currDecl.prevMin == null)
            return false;

        return prevResp + 1 < currDecl.prevMin;
    };

    hotkeys.bindTo($scope)
        .add({
            combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            description: "Select option",
            callback: function(event, hotkey) {
                var active = $scope.response.active;
                if (active < 0 || active >= $scope.response.responses.length)
                    return;

                var i = Number(String.fromCharCode(event.keyCode)) - 1;
                i = Math.max(0, i);
                i = Math.min($scope.schema.responses.length, i);
                $scope.response.responses[active] = i;
                $scope.response.active++;
            }
        })
        .add({
            combo: ['up'],
            description: "Previous response",
            callback: function(event, hotkey) {
                $scope.response.active = Math.max(0, $scope.response.active - 1);
            }
        })
        .add({
            combo: ['down'],
            description: "Next response",
            callback: function(event, hotkey) {
                $scope.response.active = Math.min($scope.response.responses.length, $scope.response.active + 1);
            }
        });
};
ResponseStandardCtrl.prototype = Object.create(BaseResponseCtrl.prototype)
