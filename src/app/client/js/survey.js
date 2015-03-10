'use strict';

angular.module('wsaa.survey', ['ngResource'])


.factory('Schema', ['$resource', function($resource) {
    return $resource('/schema/:name.json', {name: '@name'}, {
        get: { method: 'GET' }
    });
}])


.controller('SurveyCtrl', ['$scope', 'Schema',
        function($scope, Schema) {

    $scope.measure = {
        description: [
            {
                name: "Intent",
                text: "To identify the extent to which the agency has a Board/Executive team approved policy in place for capital program prioritisation. The policy should be consistent with other agency policies, refers to the key outcomes or objectives to be achieved through capital program prioritisation, outline the approach to prioritisation, and provide sufficient flexibility in unusual circumstances."
            }
        ],
        responseType: 'standard'
    };
    $scope.schema = null;

    $scope.$watch('measure.responseType', function(responseType) {
        $scope.schema = Schema.get({name: responseType});
    });

}])


.controller('ResponseStandardCtrl', ['$scope', ResponseStandardCtrl])

;


function BaseResponseCtrl($scope) {
};

function ResponseStandardCtrl($scope) {
    BaseResponseCtrl.call(this, $scope);

    $scope.$watch('schema', function(schema) {
        $scope.activeResponse = schema.responses[0];
    });
};
ResponseStandardCtrl.prototype = Object.create(BaseResponseCtrl.prototype)
