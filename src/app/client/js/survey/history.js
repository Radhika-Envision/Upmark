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
                /*if ($scope.isQnode) {
                    angular.forEach($scope.model,function(item,index)
                    {
                        let searchForQnode=angular.copy(search);
                        searchForQnode.measureId= item.id;
                        delete searchForQnode.page;
                        $scope.service.history(searchForQnode).$promise.then(
                            function success(versions) {
                                $scope.setVersions(versions);
                                if (index==$scope.model.length-1){
                                   $scope.loading = false;
                                   $scope.error = null;
                                }
                            },
                            function failure(details) {
                                $scope.loading = false;
                                $scope.error = "Could not get history: " +
                                    details.statusText;
                            }
                        );
                    })
                }
                else
                {*/
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
                //};
            }, true);

            $scope.setVersions= function(versions) {
                if ($scope.totalVersions) {
                    //$scope.versions=$scope.versions.concat(versions);

                    versions.forEach(function(item){
                        //if (!$scope.versions.some(v => v.modified === item.modified)) {
                        //    $scope.versions=$scope.versions.concat([{modified:item.modified}]);
                        //} 
                        var notFound=true;
                        let iDate=new Date(item.modified*1000);
                        $scope.totalVersions.every(function(v){
                            let vDate=new Date(v.modified*1000);
                            if (vDate.getFullYear() == iDate.getFullYear() && 
                                vDate.getMonth() == iDate.getMonth() && 
                                vDate.getDate() == iDate.getDate() ) {
                                notFound=false;
                                return  false;
                                //throw StopIteration;;
                            }
                            else {
                                return true;
                            }

                        });
                        if (notFound) {
                            $scope.totalVersions=$scope.totalVersions.concat([{modified:item.modified}]);
                        }
                    })
                } 
                else {
                    versions.forEach(function(item){
                        if ($scope.totalVersions)
                           $scope.totalVersions=$scope.totalVersions.concat([{modified:item.modified}]);                       
                        else {

                            $scope.totalVersions=[{modified:item.modified}];
                        }   
                    })
                }
                $scope.totalVersions.sort((a, b) => parseFloat(b.modified) - parseFloat(a.modified));
                $scope.page=0;
                $scope.getPage();
                /*if ($scope.totalVersions.length>0) {
                    $scope.versions=[{modified:$scope.totalVersions[0].modified}];
                    for (var i = 1; i<10; ++i) {
                        if ($scope.totalVersions.length<i) {
                            break;
                        }
                        $scope.versions=$scope.versions.concat([{modified:$scope.totalVersions[i].modified}]);    
                    }
                }*/
                //$scope.loading = false;
                //$scope.error = null;
            };

            $scope.getPage=function(){
                let first=10*$scope.page;
                let last=10+first;
                if ($scope.totalVersions.length<last) {
                    last=$scope.totalVersions.length;
                }

                if ($scope.totalVersions.length>first) {
                    $scope.versions=[{modified:$scope.totalVersions[first].modified}];
                    for (var i = first+1; i<last; ++i) {
                        if ($scope.totalVersions.length<i) {
                            break;
                        }
                        $scope.versions=$scope.versions.concat([{modified:$scope.totalVersions[i].modified}]);    
                    }
                }               

            };



            $scope.nextPage = function($event) {
                /*if ($scope.isQnode) {
                    if ($scope.page!=0) {
                        $scope.page=$scope.page-1;
                        $scope.getPage();
                     }                  
                }
                else {*/
                    if ($scope.search.page > 0)
                        $scope.search.page--;
                /*}*/
                $event.preventDefault();
                $event.stopPropagation();
            };
            $scope.prevPage = function($event) {
                /*if ($scope.isQnode) {
                     if ($scope.totalVersions.length>(10*$scope.page+10)) {
                        $scope.page=$scope.page+1;
                        $scope.getPage();                
                     }
                }
                else {*/
                if ($scope.versions.length >= $scope.search.pageSize)
                    $scope.search.page++;
                //}
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
                    /*$scope.version=version;
                    let searchForMeasure= angular.copy($scope.queryParams);
                    //searchForMeasure.measureId= item.id;
                    //delete searchForMeasure.page;

                    $scope.service.history(searchForMeasure).$promise.then(
                        function success(versions) {
                            //if no old version, keep current version 
                            if (versions && versions.length>0) {
                                // selected time older then the oldest version, display the oldest version
                                // other display the version which time firstly older then selected time 
                                $scope.version=versions[versions.length-1]; 
                                for (var i=0;i<versions.length-1;i++) {
                                    if ($scope.version.modified>=versions[i].modified) {
                                       $scope.version=versions[i];
                                       break;
                                    }
                                }*/
                                var params = angular.merge(
                                    angular.copy($scope.queryParams),
                                   // {version: $scope.version.version}
                                      {version: version.version}
                                );
                                $scope.service.get(params).$promise.then(
                                    function success(model) {
                                        if ($scope.model.subMeasures) {
                                            model.hasSubMeasures=true;
                                            model.subMeasures=$scope.model.subMeasures;
                                            model.qnodeMeasure=$scope.model.qnodeMeasure;
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
          
                        /*},
                        function failure(details) {
                            $scope.loading = false;
                            $scope.error = "Could not get history: " +
                                details.statusText;
                        }
                    );
                }*/
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
