'use strict'

angular.module('upmark.submission.response', [
    'ngResource', 'upmark.admin.settings', 'ui.select'])


.factory('Response', ['$resource', function($resource) {
    return $resource('/submission/:submissionId/response/:measureId.json',
            {submissionId: '@submissionId', measureId: '@measureId'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET',
            url: '/submission/:submissionId/response/:measureId/history.json',
            isArray: true, cache: false }
    });
}])


.factory('Attachment', ['$resource', function($resource) {
    return {
        measure : $resource('/submission/:submissionId/measure/:measureId/attachment.json',
            {submissionId: '@submissionId', measureId: '@measureId'}, {
            saveExternals: { method: 'PUT', isArray: true },
            query: { method: 'GET', isArray: true, cache: false },
            remove: { method: 'DELETE', url: '/attachment/:id', cache: false }
            }),

        submeasure: $resource('/submission/:submissionId/measure/:measureId/submeasure/:submeasureId/attachment.json',
                   {submissionId: '@submissionId', measureId: '@measureId',submeasureId:'@submeasureId'}, {
                     saveExternals: { method: 'PUT', isArray: true },
                     query: { method: 'GET', isArray: true, cache: false },
                   }
                )
    };
}])

/*.factory('Attachment', ['$resource', function($resource) {
    return $resource('/submission/:submissionId/measure/:measureId/submeasure/:submeasureId/attachment.json',
            {submissionId: '@submissionId', measureId: '@measureId',submeasureId:'@submeasureId'}, {
               // query: { method: 'GET', isArray: true, cache: false },
    });
}])*/

.controller('ResponseAttachmentCtrl',
        function($scope, Attachment, $http, $cookies, Notifications, download) {

    $scope.m = {
        attachments: null,
        activeAttachment: null,
        deletingAttachment: null,
        externals: [],
    };

    if ($scope.measure)
       $scope.responseMeasure=$scope.measure
    else
       $scope.responseMeasure=$scope.item

    var headers = {};
    var xsrfName = $http.defaults.xsrfHeaderName;
    headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);
    $scope.addExternal = function() {
        $scope.m.externals.push({"url": ""});
    }
    $scope.toggleFileDrop = function() {
        $scope.showFileDrop = !$scope.showFileDrop;
    };

    $scope.deleteExternal = function(index) {
        if (index > -1) {
            $scope.m.externals.splice(index, 1);
        }
    }

    var config = {
        url: '/',
        maxFilesize: 10,
        paramName: "file",
        headers: headers,
        // uploadMultiple: true,
        autoProcessQueue: false
    };

    //var dropzone = new Dropzone("#dropzone", config);
    var dropzoneId="#dropzone"; // +'_'+$scope.responseMeasure.seq+'_0'
    if (!document.querySelector(dropzoneId) || !document.querySelector(dropzoneId).dropzone)
         var dropzone = new Dropzone(dropzoneId, config);
     else
         var dropzone = document.querySelector(dropzoneId).dropzone;  

    $scope.save = function() {
        $scope.upload();
        if ($scope.m.externals.length > 0) {
            Attachment.measure.saveExternals({
                submissionId: $scope.submission.id,
                measureId: $scope.responseMeasure.id,
                externals: $scope.m.externals
            }).$promise.then(
                function success(attachments) {
                    $scope.m.attachments = attachments;
                    $scope.m.externals = [];
                },
                function failure(details) {
                    if ($scope.m.attachments) {
                        Notifications.set('attach', 'error',
                            "Failed to add attachments: " +
                            details.statusText);
                    }
                }
            );
        }
    }
    $scope.upload = function() {
        if (dropzone.files.length > 0) {
            dropzone.options.url = '/submission/' + $scope.submission.id +
                '/measure/' + $scope.responseMeasure.id + '/attachment.json';
            dropzone.options.autoProcessQueue = true;
            dropzone.processQueue();

        }

    };
    $scope.cancelNewAttachments = function() {
        dropzone.removeAllFiles();
        $scope.showFileDrop = false;
        $scope.m.externals = [];
    };

    $scope.$on('response-saved', $scope.save);

    $scope.refreshAttachments = function() {
        Attachment.measure.query({
            submissionId: $scope.submission.id,
            measureId: $scope.responseMeasure.id,
        }).$promise.then(
            function success(attachments) {
                $scope.m.attachments = attachments;
            },
            function failure(details) {
                if ($scope.m.attachments) {
                    Notifications.set('attach', 'error',
                        "Failed to refresh attachment list: " +
                        details.statusText);
                }
            }
        );
    };
    $scope.refreshAttachments();
    $scope.safeUrl = function(url) {
        return !! /^(https?|ftp):\/\//.exec(url);
    };
    $scope.isUpload = function(attachment) {
        return !attachment.url || attachment.storage == 'aws';
    };

    $scope.getUrl = function(attachment) {
        return '/attachment/' + attachment.id + '/' + attachment.fileName;
    };
    $scope.download = function(attachment) {
        var namePattern = /\/attachment\/[^/]+\/(.*)/;
        var url = $scope.getUrl(attachment);
        download(namePattern, url);
    };

    dropzone.on("queuecomplete", function() {
        dropzone.options.autoProcessQueue = false;
        $scope.showFileDrop = false;
        dropzone.removeAllFiles();
        $scope.refreshAttachments();
    });

    dropzone.on("error", function(file, details, request) {
        var error;
        if (request) {
            error = "Upload failed: " + request.statusText;
        } else {
            error = details;
        }
        dropzone.options.autoProcessQueue = false;
        dropzone.removeAllFiles();
        Notifications.set('attach', 'error', error);
    });
    $scope.deleteAttachment = function(attachment) {
        var isExternal = attachment.url;
        Attachment.measure.remove({id: attachment.id}).$promise.then(
            function success() {
                var message;
                if (!isExternal) {
                    message = "The attachment was removed, but it can not be " +
                              "deleted from the database.";
                } else {
                    message = "Link removed.";
                }
                Notifications.set('attach', 'success', message, 5000);
                $scope.refreshAttachments();
            },
            function failure(details) {
                Notifications.set('attach', 'error',
                    "Could not delete attachment: " + details.statusText);
            }
        );
    };
})

.controller('ResponseForMeasureAttachmentCtrl',
        function($scope, Attachment, $http, $cookies, Notifications, download,  $element) {

        $scope.init = function(submissionId, subMeasureId, seq, index, measureId) {
    
              //This function is sort of private constructor for controller
              
              if (!seq)
                  seq=0;
              //$scope.dropzoneListId='#dropzone-'+seq+'-'+index;
              $scope.dropzoneListId='#dropzone-'+subMeasureId;
              $scope.submission={id: submissionId};
              $scope.measure={
                  id:subMeasureId,     //submeasure id
                  measureId:measureId  // measure id
              };
              $scope.refreshAttachments();
              //Based on passed argument you can make a call to resource
              //and initialize more objects
  
        };
        
        $scope.initAttachment=function (index,last){
            $scope.attachementIndex=index;
            /*var config = {
                url: '/',
                maxFilesize: 10,
                paramName: "file",
                headers: headers,
                // uploadMultiple: true,
                autoProcessQueue: false
            };*/
            
            /*if (!document.querySelector("#dropzone") || !document.querySelector("#dropzone").dropzone)
               var dropzone = new Dropzone("#dropzone", config);
            else
               var dropzone = document.querySelector("#dropzone").dropzone;  */ 
            /*var dropzone = new Dropzone("#dropzone"+index, config);
            dropzone.on("queuecomplete", function() {
                dropzone.options.autoProcessQueue = false;
                $scope.showFileDrop = false;
                dropzone.removeAllFiles();
                $scope.refreshAttachments();
            });
        
            dropzone.on("error", function(file, details, request) {
                var error;
                if (request) {
                    error = "Upload failed: " + request.statusText;
                } else {
                    error = details;
                }
                dropzone.options.autoProcessQueue = false;
                dropzone.removeAllFiles();
                Notifications.set('attach', 'error', error);
            });*/
     };

    $scope.m = {
        attachments: null,
        activeAttachment: null,
        deletingAttachment: null,
        externals: [],
    };

    var headers = {};
    var xsrfName = $http.defaults.xsrfHeaderName;
    headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);
    $scope.addExternal = function() {
        $scope.m.externals.push({"url": ""});
    }
    $scope.toggleFileDrop = function() {
        $scope.showFileDrop = !$scope.showFileDrop;
    };

    $scope.deleteExternal = function(index) {
        if (index > -1) {
            $scope.m.externals.splice(index, 1);
        }
    }

    var config = {
        url: '/',
        maxFilesize: 10,
        paramName: "file",
        headers: headers,
        // uploadMultiple: true,
        autoProcessQueue: false
    };
    
    angular.element(document).ready(function () {
        var dropzone = new Dropzone($scope.dropzoneListId, config);
        dropzone.on("queuecomplete", function() {
            dropzone.options.autoProcessQueue = false;
            $scope.showFileDrop = false;
            dropzone.removeAllFiles();
            $scope.refreshAttachments();
        });
    
        dropzone.on("error", function(file, details, request) {
            var error;
            if (request) {
                error = "Upload failed: " + request.statusText;
            } else {
                error = details;
            }
            dropzone.options.autoProcessQueue = false;
            dropzone.removeAllFiles();
            Notifications.set('attach', 'error', error);
        });

        $scope.cancelNewAttachments = function() {
            dropzone.removeAllFiles();
            $scope.showFileDrop = false;
            $scope.m.externals = [];
        };
    });

    $scope.saveResponse = function() {
        $scope.$emit("saveResponse");
        /*return $scope.model.response.$save().then(
            function success(response) {
                $scope.$broadcast('response-saved');
                Notifications.set('edit', 'success', "Saved", 5000);
                $scope.setResponse(response);
                return response;
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
                return $q.reject(details);
            });*/
    };

    

    $scope.save = function() {
        $scope.upload();
        if ($scope.m.externals.length > 0) {
            Attachment.submeasure.saveExternals({
                submissionId: $scope.submission.id,
                measureId: $scope.measure.measureId,
                submeasureId: $scope.measure.id,
                externals: $scope.m.externals
            }).$promise.then(
                function success(attachments) {
                    $scope.m.attachments = attachments;
                    $scope.m.externals = [];
                },
                function failure(details) {
                    if ($scope.m.attachments) {
                        Notifications.set('attach', 'error',
                            "Failed to add attachments: " +
                            details.statusText);
                    }
                }
            );
        }
    }
    $scope.upload = function() {
        var dropzone=document.querySelector($scope.dropzoneListId).dropzone;
        if (dropzone.files.length > 0) {
            dropzone.options.url = '/submission/' + $scope.submission.id +
                '/measure/' + $scope.measure.measureId  +'/submeasure/' + $scope.measure.id  +  '/attachment.json';
            //dropzone.options.url = '/submission/' + $scope.submission.id +
            //    '/measure/' + angular.toJson($scope.measure.measureId)  + '/attachment.json';
            dropzone.options.autoProcessQueue = true;
            dropzone.processQueue();
        }
    };


    $scope.$on('response-saved', $scope.save);

    $scope.refreshAttachments = function() {
        if ($scope.measure.id) {
            Attachment.submeasure.query({
                submissionId: $scope.submission.id,
                measureId: $scope.measure.measureId, // measure id
                submeasureId:$scope.measure.id, //submeasure id
            }).$promise.then(
                function success(attachments) {
                     $scope.m.attachments = attachments;
                },
                function failure(details) {
                    if ($scope.m.attachments) {
                        Notifications.set('attach', 'error',
                             "Failed to refresh attachment list: " +
                            details.statusText);
                    }
                }
            );
        }
    };
    //$scope.refreshAttachments();
    $scope.safeUrl = function(url) {
        return !! /^(https?|ftp):\/\//.exec(url);
    };
    $scope.isUpload = function(attachment) {
        return !attachment.url || attachment.storage == 'aws';
    };

    $scope.getUrl = function(attachment) {
        return '/attachment/' + attachment.id + '/' + attachment.fileName;
    };
    $scope.download = function(attachment) {
        var namePattern = /\/attachment\/[^/]+\/(.*)/;
        var url = $scope.getUrl(attachment);
        download(namePattern, url);
    };

  
    /*dropzone.on("queuecomplete", function() {
        dropzone.options.autoProcessQueue = false;
        $scope.showFileDrop = false;
        dropzone.removeAllFiles();
        $scope.refreshAttachments();
    });

    dropzone.on("error", function(file, details, request) {
        var error;
        if (request) {
            error = "Upload failed: " + request.statusText;
        } else {
            error = details;
        }
        dropzone.options.autoProcessQueue = false;
        dropzone.removeAllFiles();
        Notifications.set('attach', 'error', error);
    });*/


    $scope.deleteAttachment = function(attachment) {
        var isExternal = attachment.url;
        Attachment.measure.remove({id: attachment.id}).$promise.then(
            function success() {
                var message;
                if (!isExternal) {
                    message = "The attachment was removed, but it can not be " +
                              "deleted from the database.";
                } else {
                    message = "Link removed.";
                }
                Notifications.set('attach', 'success', message, 5000);
                $scope.refreshAttachments();
            },
            function failure(details) {
                Notifications.set('attach', 'error',
                    "Could not delete attachment: " + details.statusText);
            }
        );
    };
})

.directive('responseForm', function() {
    return {
        restrict: 'E',
        scope: {
            rt: '=type',
            response: '=model',
            weight_: '=weight',
            readonly: '=',
            hasQuality: '=',
            externs: '=',
            isDummy: '@',
        },
        replace: true,
        templateUrl: 'response_form.html',
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Authz', 'Enqueue',
                function($scope, hotkeys, Authz, Enqueue) {
            $scope.$watch('weight_', function(weight) {
                $scope.weight = weight == null ? 100 : weight;
            });

            $scope.state = {
                variables: null,
                score: 0,
                active: 0
            };

            var recalculate = Enqueue(function() {
                if ($scope.isDummy)
                    return;
                    
                angular.forEach($scope.$parent.$parent.$parent.$parent.$parent.$parent.$parent.questionList, function(q,i){  
               
                       var rt = q.rt,
                       partsR = q.response.responseParts;

                       if (!rt || !partsR) {
                           q.state.score = 0;
                           q.state.active = 0;
                           q.state.message = 'Loading';
                           return;
                        }
                        rt.parts.forEach(function(part, i) {
                           if (!partsR[i])
                              partsR[i] = {};
                        });

                        if (q.response.notRelevant) {
                            q.state.variables = angular.merge({}, $scope.externs);
                            q.state.score = 0;
                        } else {
                            q.state.variables = angular.merge(
                              {}, $scope.externs, rt.variables(partsR, true));
                             var mergeVariables=$scope.mergeVariables();
                        try {
                            //check responses depend on choose
                            rt.validateResponses(partsR, mergeVariables);

                            rt.validate(partsR, mergeVariables);
                            q.state.score = rt.score(
                                partsR, mergeVariables);
                            q.state.message = null;
                        } catch (e) {
                             q.state.message = '' + e;
                             q.state.score = 0;
                        }

                    /*$scope.state.variables = angular.merge(
                        {}, $scope.externs, rt.variables(partsR, true));
                    try {
                        rt.validate(partsR, $scope.state.variables);
                        $scope.state.score = rt.score(
                            partsR, $scope.state.variables);
                        $scope.state.message = null;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                    }*/
  
                }
                })
            }, 0, $scope);

           /* var recalculate = Enqueue(function() {
                if ($scope.isDummy)
                    return;
                var rt = $scope.rt,
                    partsR = $scope.response.responseParts;

                if (!rt || !partsR) {
                    $scope.state.score = 0;
                    $scope.state.active = 0;
                    $scope.state.message = 'Loading';
                    return;
                }
                rt.parts.forEach(function(part, i) {
                    if (!partsR[i])
                        partsR[i] = {};
                });

                if ($scope.response.notRelevant) {
                    $scope.state.variables = angular.merge({}, $scope.externs);
                    $scope.state.score = 0;
                } else {
                    $scope.state.variables = angular.merge(
                        {}, $scope.externs, rt.variables(partsR, true));
                    var mergeVariables=$scope.mergeVariables();
                    try {
                        rt.validate(partsR, mergeVariables);
                        $scope.state.score = rt.score(
                            partsR, mergeVariables);
                        $scope.state.message = null;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                    }*/

                    /* //$scope.state.variables = angular.merge(
                        {}, $scope.externs, rt.variables(partsR, true));
                    try {
                        rt.validate(partsR, $scope.state.variables);
                        $scope.state.score = rt.score(
                            partsR, $scope.state.variables);
                        $scope.state.message = null;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                    }//*/
              /*  }
            }, 0, $scope);*/
            $scope.$watch('rt', recalculate);
            $scope.$watch('response.responseParts', recalculate, true);
            $scope.$watch('externs', recalculate, true);

            $scope.getPartData = function(partSchema) {
                if ($scope.isDummy)
                    return;
                var i = $scope.rt.parts.indexOf(partSchema);
                return $scope.response.responseParts[i];
            };

            $scope.choose = function(partSchema, option) {
                //$scope.$parent.$parent.$parent.$parent.$parent.$parent.$parent.questionList
                var partData = $scope.getPartData(partSchema);
                partData.index = partSchema.options.indexOf(option);
                partData.note = option.name;
                var nParts = $scope.rt.parts.length;
                var iPart = $scope.rt.parts.indexOf(partSchema);
                $scope.state.active = Math.min(iPart + 1, nParts - 1);

                // change other answer which affect by this answer
                /*angular.forEach($scope.$parent.$parent.$parent.$parent.$parent.$parent.$parent.questionList, function(q,i){  
                    if (i>1) {  
                       var rt = q.rt,
                       partsR = q.response.responseParts;
                   
                      if (q.response.notRelevant==undefined || !q.response.notRelevant) {
                        var mergeVariables=$scope.mergeVariables();*/
                        /*try {
                            rt.validate(partsR, mergeVariables);
                          
                            q.state.score = rt.score(
                                partsR, mergeVariables);
                            q.state.message = null;
                        } catch (e) {*/
                            // make sure not available partsR.part should select first option
                         /*   if (mergeVariables)
                               rt.validate(partsR, mergeVariables);
                               rt.validateForSelect(partsR, mergeVariables);*/
                         /*   q.state.message = '' + e;
                            q.state.score = 0;
                        }*/
    
                      //}
                    //}


                //})

                // add all variables of submeasure togather
                /*if ($scope.$parent.$parent.$parent.$parent.$parent.$parent) 
                {
                   var variables={};
                   angular.forEach($scope.$parent.$parent.$parent.$parent.$parent.$parent.$parent.questionList, function(q,i){
                    //first 2 not questions   
                      if (i==2) {
                        variables= angular.merge({}, q.state.variables);
                      }
                      else if (i>2) {
                        variables=angular.merge(variables, q.state.variables);
                    }
                    

                   })
                   $scope.state.variables=variables;
                   if ($scope.state.variables.length==0)
                      $scope.state.variables=null;
                }  */              
            };
            $scope.available = function(option) {
                var mergeVariables=$scope.mergeVariables();
                /*if ($scope.$parent.$parent.$parent.$parent.$parent.$parent) 
                {
                   
                   angular.forEach($scope.$parent.$parent.$parent.$parent.$parent.$parent.$parent.questionList, function(q,i){
                        //first 2 not questions   
                        if (q.state.variables) {
                           if (i==2 ) {
                                 mergeVariables= angular.merge({}, q.state.variables);
                            }
                            else if (i>2) {
                                 mergeVariables=angular.merge(mergeVariables, q.state.variables);
                            }
                
                        }

                    })
                }    */         
                //if (!$scope.state.variables)
                if (!mergeVariables)
                    return false;
                //return option.available($scope.state.variables);
             
                return option.available(mergeVariables);
            };

            $scope.mergeVariables=function(){
                if ($scope.isDummy)
                   return false; 
                var mergeVariables=null;
                if ($scope.$parent.$parent.$parent.$parent.$parent.$parent) 
                {
               
                    angular.forEach($scope.$parent.$parent.$parent.$parent.$parent.$parent.$parent.questionList, function(q,i){

                        if (q.state.variables) {
                            if (i==0) {
                                 mergeVariables= angular.merge({}, q.state.variables);
                            }
                            else if (i>0) {
                                 mergeVariables=angular.merge(mergeVariables, q.state.variables);
                            }
            
                        }

                    })
                } 
                return mergeVariables;
            }



            $scope.isFinite = isFinite;

            $scope.checkRole = Authz({program: $scope.program});

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.which)) - 1;
                        i = Math.max(0, i);
                        i = Math.min($scope.rt.parts.length, i);
                        var partSchema = $scope.rt.parts[$scope.state.active];
                        var option = partSchema.options[i];
                        $scope.choose(partSchema, option);
                    }
                })
                .add({
                    combo: ['-', '_'],
                    description: "Previous response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.max(
                            0, $scope.state.active - 1);
                    }
                })
                .add({
                    combo: ['+', '='],
                    description: "Next response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.min(
                            $scope.rt.parts.length - 1,
                            $scope.state.active + 1);
                    }
                })
                .add({
                    combo: ['c'],
                    description: "Edit comment",
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('focus-comment');
                    }
                })
                .add({
                    combo: ['esc'],
                    description: "Stop editing comment (only in plain text mode)",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
            if (!attrs.isResponse) {
                if (scope.isDummy) {
                    scope.$parent.$parent.$parent.$parent.$parent.questionList=[];
                }
                else if (attrs.isResponseType) {
                    if (scope.$parent.$parent.$parent.$parent.$parent.questionList) {
                        scope.$parent.$parent.$parent.$parent.$parent.questionList.push(scope);
                    }
                    else {
                        scope.$parent.$parent.$parent.$parent.$parent.questionList=[scope];
                    }
                }
            }
        }
    }
                                      })



.directive('responsesForm', function() {
    return {
        restrict: 'E',
        scope: {
            rt: '=type',
            response: '=model',
            weight_: '=weight',
            readonly: '=',
            hasQuality: '=',
            externs: '=',
            isDummy: '@',
        },
        replace: true,
        templateUrl: 'responses_form.html',
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Authz', 'Enqueue',
                function($scope, hotkeys, Authz, Enqueue) {
            $scope.$watch('weight_', function(weight) {
                $scope.weight = weight == null ? 100 : weight;
            });

            $scope.state = {
                variables: null,
                score: 0,
                active: 0
            };

            var recalculate = Enqueue(function() {
                if ($scope.isDummy)
                    return;
                var rt = $scope.rt,
                    partsR = $scope.response.responseParts;

                if (!rt || !partsR) {
                    $scope.state.score = 0;
                    $scope.state.active = 0;
                    $scope.state.message = 'Loading';
                    return;
                }
                rt.parts.forEach(function(part, i) {
                    if (!partsR[i])
                        partsR[i] = {};
                });

                if ($scope.response.notRelevant) {
                    $scope.state.variables = angular.merge({}, $scope.externs);
                    $scope.state.score = 0;
                } else {
                    $scope.state.variables = angular.merge(
                        {}, $scope.externs, rt.variables(partsR, true));
                    try {
                        rt.validate(partsR, $scope.state.variables);
                        $scope.state.score = rt.score(
                            partsR, $scope.state.variables);
                        $scope.state.message = null;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                    }
                }
            }, 0, $scope);
            $scope.$watch('rt', recalculate);
            $scope.$watch('response.responseParts', recalculate, true);
            $scope.$watch('externs', recalculate, true);

            $scope.getPartData = function(partSchema) {
                if ($scope.isDummy)
                    return;
                var i = $scope.rt.parts.indexOf(partSchema);
                return $scope.response.responseParts[i];
            };

            $scope.choose = function(partSchema, option) {
                var partData = $scope.getPartData(partSchema);
                partData.index = partSchema.options.indexOf(option);
                partData.note = option.name;
                var nParts = $scope.rt.parts.length;
                var iPart = $scope.rt.parts.indexOf(partSchema);
                $scope.state.active = Math.min(iPart + 1, nParts - 1);
            };
            $scope.available = function(option) {
                if (!$scope.state.variables)
                    return false;
                return option.available($scope.state.variables);
            };
            $scope.isFinite = isFinite;

            $scope.checkRole = Authz({program: $scope.program});

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.which)) - 1;
                        i = Math.max(0, i);
                        i = Math.min($scope.rt.parts.length, i);
                        var partSchema = $scope.rt.parts[$scope.state.active];
                        var option = partSchema.options[i];
                        $scope.choose(partSchema, option);
                    }
                })
                .add({
                    combo: ['-', '_'],
                    description: "Previous response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.max(
                            0, $scope.state.active - 1);
                    }
                })
                .add({
                    combo: ['+', '='],
                    description: "Next response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.min(
                            $scope.rt.parts.length - 1,
                            $scope.state.active + 1);
                    }
                })
                .add({
                    combo: ['c'],
                    description: "Edit comment",
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('focus-comment');
                    }
                })
                .add({
                    combo: ['esc'],
                    description: "Stop editing comment (only in plain text mode)",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
            /*if (scope.isDummy) {
                scope.$parent.$parent.$parent.$parent.$parent.$parent=[];
            }
            else {
                if (scope.$parent.$parent.$parent.$parent.$parent.$parent.questionList) {
                   scope.$parent.$parent.$parent.$parent.$parent.$parent.questionList.push(scope);
                }
                else {
                   scope.$parent.$parent.$parent.$parent.$parent.$parent.questionList=[scope];
                }
            }*/
        }
    }
                                      })

.directive('responseSubForm', function() {
    return {
        restrict: 'E',
        scope: {
            rt: '=type',
            response: '=model',
            weight_: '=weight',
            readonly: '=',
            hasQuality: '=',
            externs: '=',
            isDummy: '@',
        },
        replace: true,
        templateUrl: 'response_sub_form.html',
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Authz', 'Enqueue',
                function($scope, hotkeys, Authz, Enqueue) {

        //put submeasure seq, description, comment, attachement to responseType
        
        /*if ($scope.response.subMeasures && $scope.response.subMeasures.length>0) {
                 var lastSubmeasureId=null;
                 var subSeq=1;
                 if ($scope.rt && $scope.rt.parts && $scope.rt.parts.length>0) {
                     $scope.rt.parts.forEach(function(item,index){
                    if (lastSubmeasureId!=item.submeasure) {
                       if (lastSubmeasureId) {
                           $scope.rt.parts[index-1].comment="";
                        }
                        $scope.response.subMeasures.forEach(function(sub,i){
                        if (sub.id==item.submeasure) {
                            item.subDesc=sub.description;
                            item.subSeq=subSeq;
                            subSeq=subSeq+1;
                        } 
                        lastSubmeasureId=item.submeasure;
                    });

                }
            })
            $scope.rt.parts[$scope.rt.parts.length-1].comment="";
            }
        }
        if ($scope.response.measure && $scope.response.measure.parents && $scope.response.measure.parents.length>0) {
            $scope.response.parentSeq=($scope.response.measure.parents[0].seq+1)+'.';
        }
        else {
            $scope.response.parentSeq='';
        }*/

        
        // end of put submeasure seq, description, comment, attachement to responseType



            $scope.$watch('weight_', function(weight) {
                $scope.weight = weight == null ? 100 : weight;
            });

            $scope.state = {
                variables: null,
                score: 0,
                active: 0
            };

            var recalculate = Enqueue(function() {
                if ($scope.isDummy)
                    return;

                //put submeasure seq, description, comment, attachement to responseType
                if ($scope.response.subMeasures && $scope.response.subMeasures.length>0) {
                        var lastSubmeasureId=null;
                        var subSeq=1;
                        if ($scope.rt && $scope.rt.parts && $scope.rt.parts.length>0) {
                            $scope.rt.parts.forEach(function(item,index){
                           if (lastSubmeasureId!=item.submeasure) {
                              if (lastSubmeasureId) {
                                  $scope.rt.parts[index-1].comment="";
                               }
                               $scope.response.subMeasures.forEach(function(sub,i){
                               if (sub.id==item.submeasure) {
                                   item.subDesc=sub.description;
                                   item.subSeq=subSeq;
                                   subSeq=subSeq+1;
                               } 
                               lastSubmeasureId=item.submeasure;
                           });
       
                        }
                        $scope.response.questions=subSeq;
                   })
                   $scope.rt.parts[$scope.rt.parts.length-1].comment="";
                   }
                }
                else
                {
                    $scope.response.questions=1;
                }
                if ($scope.response.measure && $scope.response.measure.parents && $scope.response.measure.parents.length>0) {
                    $scope.response.parentSeq=($scope.response.measure.parents[0].seq+1)+'.';
               }
               else {
                   $scope.response.parentSeq='';
                }
                
                // end of put submeasure seq, description, comment, attachement to responseType

                var rt = $scope.rt,
                    partsR = $scope.response.responseParts;

                if (!rt || !partsR) {
                    $scope.state.score = 0;
                    $scope.state.active = 0;
                    $scope.state.message = 'Loading';
                    return;
                }
                rt.parts.forEach(function(part, i) {
                    if (!partsR[i])
                        partsR[i] = {};
                });

                if ($scope.response.notRelevant) {
                    $scope.state.variables = angular.merge({}, $scope.externs);
                    $scope.state.score = 0;
                    $scope.response.answerQuestons=$scope.response.questons;
                } else {
                    $scope.state.variables = angular.merge(
                        {}, $scope.externs, rt.variables(partsR, true));
                    try {
                        rt.validate(partsR, $scope.state.variables);
                        $scope.state.score = rt.score(
                            partsR, $scope.state.variables);
                        $scope.state.message = null;
                        $scope.response.answerQuestons=$scope.response.questons;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                        $scope.response.answerQuestons=0;
                    }
                }
                $scope.response.score=$scope.state*$scope.weight;
            }, 0, $scope);
            $scope.$watch('rt', recalculate);
            $scope.$watch('response.responseParts', recalculate, true);
            $scope.$watch('externs', recalculate, true);

            $scope.getPartData = function(partSchema) {
                if ($scope.isDummy)
                    return;
                var i = $scope.rt.parts.indexOf(partSchema);
                return $scope.response.responseParts[i];
            };

            $scope.choose = function(partSchema, option) {
                var partData = $scope.getPartData(partSchema);
                partData.index = partSchema.options.indexOf(option);
                partData.note = option.name;
                var nParts = $scope.rt.parts.length;
                var iPart = $scope.rt.parts.indexOf(partSchema);
                $scope.state.active = Math.min(iPart + 1, nParts - 1);
            };
            $scope.available = function(option) {
                if (!$scope.state.variables)
                    return false;
                return option.available($scope.state.variables);
            };
            $scope.isFinite = isFinite;

            $scope.checkRole = Authz({program: $scope.program});

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.which)) - 1;
                        i = Math.max(0, i);
                        i = Math.min($scope.rt.parts.length, i);
                        var partSchema = $scope.rt.parts[$scope.state.active];
                        var option = partSchema.options[i];
                        $scope.choose(partSchema, option);
                    }
                })
                .add({
                    combo: ['-', '_'],
                    description: "Previous response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.max(
                            0, $scope.state.active - 1);
                    }
                })
                .add({
                    combo: ['+', '='],
                    description: "Next response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.min(
                            $scope.rt.parts.length - 1,
                            $scope.state.active + 1);
                    }
                })
                .add({
                    combo: ['c'],
                    description: "Edit comment",
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('focus-comment');
                    }
                })
                .add({
                    combo: ['esc'],
                    description: "Stop editing comment (only in plain text mode)",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
            /*if (scope.isDummy) {
                scope.$parent.$parent.$parent.$parent.$parent.$parent=[];
            }
            else {
                if (scope.$parent.$parent.$parent.$parent.$parent.$parent.questionList) {
                   scope.$parent.$parent.$parent.$parent.$parent.$parent.questionList.push(scope);
                }
                else {
                   scope.$parent.$parent.$parent.$parent.$parent.$parent.questionList=[scope];
                }
            }*/
        }
    }

})                                      
                                      
.directive('ngElementReady', [function() {
    return {
        priority: Number.MIN_SAFE_INTEGER, // execute last, after all other directives if any.
        restrict: "A",
        link: function($scope, $element, $attributes) {
            //$scope.$eval($attributes.ngElementReady); // execute the expression in the attribute.
            var config = {
                url: '/',
                maxFilesize: 10,
                paramName: "file",
                //headers: headers,
                // uploadMultiple: true,
                autoProcessQueue: false
            };
            var dropzone = new Dropzone($element, config);
            dropzone.on("queuecomplete", function() {
                dropzone.options.autoProcessQueue = false;
                $scope.showFileDrop = false;
                dropzone.removeAllFiles();
                $scope.refreshAttachments();
            });
        
            dropzone.on("error", function(file, details, request) {
                var error;
                if (request) {
                    error = "Upload failed: " + request.statusText;
                } else {
                    error = details;
                }
                dropzone.options.autoProcessQueue = false;
                dropzone.removeAllFiles();
                Notifications.set('attach', 'error', error);
            });
        }
    };
}]);
;
