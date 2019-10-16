'use strict'

angular.module('upmark.survey.history', [
    'upmark.notifications'])


.directive('history', function() {
    return {
        restrict: 'E',
        scope: {
            model: '=model',
            service: '=service',
            queryParams: '=queryParams',
            itemTemplateUrl: '@itemTemplateUrl',
            isQnode: '@',
        },
        templateUrl: '/history.html',
        controller: function($scope, Notifications) {

            $scope.state = {
                isOpen: false,
            };
            $scope.$watch('state.isOpen', function(isOpen) {
                if (isOpen) {
                    $scope.search = angular.merge(
                        angular.copy($scope.queryParams),
                        {page: 0, pageSize: 10}
                    );
                } else {
                    $scope.search = null;
                    $scope.versions = null;
                }
            });
            $scope.$watch('model', function(model) {
                if (!model)
                    $scope.state.isOpen = false;
            });

            $scope.$watch('search', function(search) {
                if (!search)
                    return;
                $scope.loading = true;
                $scope.error = null;
                $scope.service.history(search).$promise.then(
                    function success(versions) {
                        $scope.versions = versions;
                        $scope.loading = false;
                        $scope.error = null;
                    },
                    function failure(details) {
                        $scope.loading = false;
                        $scope.error = "Could not get history: " +
                            details.statusText;
                    }
                );
            }, true);

            $scope.nextPage = function($event) {
                if ($scope.search.page > 0)
                    $scope.search.page--;
                $event.preventDefault();
                $event.stopPropagation();
            };
            $scope.prevPage = function($event) {
                if ($scope.versions.length >= $scope.search.pageSize)
                    $scope.search.page++;
                $event.preventDefault();
                $event.stopPropagation();
            };

            $scope.navigate = function(version) {
                if ($scope.isQnode)
                {
                    //$scope.$broadcast('show-history',  version);
                    $scope.$emit('get-history-fromQnode',  version);
                }
                else
                {
                var params = angular.merge(
                    angular.copy($scope.queryParams),
                    {version: version.version}
                );
                $scope.service.get(params).$promise.then(
                    function success(model) {
                        if ($scope.model.subMeasures) {
                            model.hasSubMeasures=true;
                            model.subMeasures=$scope.model.subMeasures;
                        }

                        $scope.model = model;
                        $scope.error = null;
                        $scope.versions = null;
                    },
                    function failure(details) {
                        $scope.error = "Could not get history: " +
                            details.statusText;
                    }
                );
                }
            };

            /*$scope.$on('show-history', function(event, version) {
                if (!$scope.isQnode)
                {
                    $scope.navigate(version);
                }
            });*/

            $scope.$on('get-history', function(event, version) {
                if (!$scope.isQnode)
                {
                    $scope.navigate(version);
                }
            });

            $scope.isActive = function(version) {
                if (!$scope.model)
                    return false;
                return version.version == $scope.model.version;
            };
        },
        link: function(scope, elem, attrs) {
            scope.$watch('model', function(model) {
                elem.css('display', model ? '' : 'none');
            });
            elem.css('display', scope.model ? '' : 'none');
        },
    };
});
