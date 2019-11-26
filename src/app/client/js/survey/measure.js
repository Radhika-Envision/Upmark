'use strict';

angular.module('upmark.survey.measure', [
    'upmark.response.type', 'upmark.structure', 'upmark.user', 'upmark.chain'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/measures', {
            templateUrl : 'measure_list.html',
            controller : 'MeasureListCtrl',
            resolve: {routeData: chainProvider({
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
            })}
        })
        .when('/:uv/measure/new', {
            templateUrl : 'measure.html',
            controller : 'MeasureCtrl',
            resolve: {routeData: chainProvider({
                parent: ['QuestionNode', '$route',
                        function(QuestionNode, $route) {
                    if (!$route.current.params.parent)
                        return null;
                    return QuestionNode.get({
                        id: $route.current.params.parent,
                        programId: $route.current.params.program
                    }).$promise;
                }],
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
            })}
        })
        .when('/:uv/measure/:measure', {
            templateUrl : 'measure.html',
            controller : 'MeasureCtrl',
            resolve: {routeData: chainProvider({
                submission: ['Submission', '$route',
                        function(Submission, $route) {
                    if (!$route.current.params.submission)
                        return null;
                    return Submission.get({
                        id: $route.current.params.submission
                    }).$promise;
                }],
                measure: ['Measure', '$route', 'submission',
                        function(Measure, $route, submission) {
                    return Measure.get({
                        id: $route.current.params.measure,
                        programId: submission ? submission.program.id :
                            $route.current.params.program,
                        surveyId: submission ? submission.survey.id :
                            $route.current.params.survey,
                        submissionId: $route.current.params.submission
                    }).$promise;
                }],
                responseType: ['measure', 'ResponseType',
                        function(measure, ResponseType) {
                    return ResponseType.get({
                        id: measure.responseTypeId,
                        programId: measure.programId
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/measure-link', {
            templateUrl : 'measure_link.html',
            controller : 'MeasureLinkCtrl',
            resolve: {routeData: chainProvider({
                parent: ['QuestionNode', '$route',
                        function(QuestionNode, $route) {
                    return QuestionNode.get({
                        id: $route.current.params.parent,
                        programId: $route.current.params.program
                    }).$promise;
                }],
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
            })}
        })
    ;
})

.factory('Measure', ['$resource', 'paged', function($resource, paged) {
    return $resource('/measure/:id.json?surveyId=:surveyId', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        reorder: { method: 'PUT', isArray: true },
        history: { method: 'GET', url: '/measure/:id/program.json',
            isArray: true, cache: false }
    });
}])


.controller('MeasureCtrl', function(
        $scope, Measure, routeData, Editor, Authz,
        $location, Notifications, currentUser, Program, format, layout,
        Structure, Arrays, Response, hotkeys, $q, $timeout, $window,
        responseTypes, ResponseType, Enqueue, $rootScope) {
    /*if ($rootScope.questions) {
        delete $rootScope.questions;
    }
    if ($rootScope.rts) {
        delete $rootScope.rts;
    } 
    if ($rootScope.externs) {
        delete $rootScope.externs;
    }
    if ($rootScope.indexSub) {
        delete $rootScope.indexSub;
    }  */
    $scope.layout = layout;
    $scope.parent = routeData.parent;
    $scope.submission = routeData.submission;
    $scope.Response = Response;
    $scope.model = {
        response: null,
        lastSavedResponse: null,
    };

    if (routeData.measure) {
        // Editing old
        $scope.measure = routeData.measure;
        // check hasSubmeasure from response_type 
        if (routeData.responseType && routeData.responseType.parts.length>0 
            && routeData.responseType.parts[0]['submeasure']){
                $scope.measure.hasSubMeasures=true;
                $scope.measure.rt=routeData.responseType;
                /*$scope.measure.subMeasureList.forEach(function(sub,i){
                    if ($rootScope.questions) {
                        $rootScope.questions.push({})
                    }
                    else
                    {
                        $rootScope.questions=[{}]
                    }
                    if ($rootScope.rts) {
                        $rootScope.rts.push({})
                    }
                    else
                    {
                        $rootScope.rts=[{}]
                    }
                });*/

                // create SubMeasures
                var subMeasures=[];
                var submeasure_id=[];
                var partObject=null;
                angular.forEach(routeData.responseType.parts,function(item,index){
                    if (item.type == 'multiple_choice') {
                        partObject=new responseTypes.MultipleChoice(item);
                    }
                    else if (item.type == 'numerical') {
                        partObject=new responseTypes.Numerical(item);
                    } 
                    partObject.submeasure= item['submeasure'];               
                    if (subMeasures.length==0) {
                        $scope.measure.subMeasureList.forEach(function(sub,i){
                            if (sub.id==item.submeasure) {
                                subMeasures.push({ 'id':item['submeasure'],
                                'description': sub['description'],
                                'rt':{'definition':{'parts':[item],'name':sub['title']},
                                      'responseType': routeData.responseType || null,
                                      search: {
                                        programId: $scope.measure.programId,
                                        pageSize: 5,
                                       }  
                                    },
                                'rtRead':{'definition':{'parts':[partObject],'name':sub['title']}},
                                'name': sub['title'],                         
                               })
                            }
                       
                        })
                    }
                    else
                    {
                        var notFoundSubmeasure=true;
                        angular.forEach(subMeasures,function(s,i){
                            if (s.id==item['submeasure']){   
                                s.rt.definition.parts.push(item);
                                s.rtRead.definition.parts.push(partObject);
                                notFoundSubmeasure=false;
                            }

                        })
                        if (notFoundSubmeasure) {
                            $scope.measure.subMeasureList.forEach(function(sub,i){
                                if (sub.id==item.submeasure) {
                                    subMeasures.push({ 'id':item['submeasure'],
                                    'description': sub['description'],
                                    'rt':{
                                            'definition':{'parts':[item],'name':sub['title']},
                                            'responseType': routeData.responseType || null ,
                                            search: {
                                              programId: $scope.measure.programId,
                                              pageSize: 5,
                                            } 
                                    },
                                    'rtRead':{'definition':{'parts':[partObject],'name':sub['title']}},
                                    'name': sub['title'],
                                   })
                                }
                           
                            })                            
                            /*subMeasures.push({ 'id':item['submeasure'],
                                  'description':item['description'],
                                  'rt':{'definition':{'parts':[item]}}
                            })*/
                        }
                    }
                    

                })
                $scope.measure['subMeasures']=subMeasures;


                // update SubMeasures
             //   angular.forEach(routeData.responseType.parts,function(item,index){
             //       /*if (subMeasures.length==0) {                        
             //           subMeasures.push({ 'id':item['submeasure'],
             //                             'description': item['description'],
             //                             'rt':{'definition':{'parts':[item]}}
             //          })
             //       }
             //       else
             //       {*/
             //           var notFoundSubmeasure=true;
             //          angular.forEach($scope.measure.subMeasures,function(sub,i){
             //               if (sub.id==item.submeasure){
             //                   if (sub.rt && sub.rt.definition && sub.rt.definition.parts) {
             //                      sub.rt.definition.parts.push(item);
             //                   }
             //                   else {
             //                       sub.rt={'definition':{'parts':[item]}};
             //                   }

             //                   notFoundSubmeasure=false;
             //               }

             //           })
             //           if (notFoundSubmeasure) {
             //               subMeasures.push({ 'id':item['submeasure'],
             //                     'description':item['description'],
             //                     'rt':{'definition':{'parts':[item]}}
             //               })
             //           }
             //       //}
                    

             //   })
             //   //$scope.measure['subMeasures']=subMeasures;

            }

    } 
    else {
        // Creating new
        $scope.measure = new Measure({
            obType: 'measure',
            parent: routeData.parent,
            programId: routeData.program.id,
            weight: 100,
            hasSubMeasures: false,
            subMeasures: [],
            responseTypeId: null,
            sourceVars: [],
            rt:{ formula: 'a'}
        })
        //$scope.edit.model.rt.formula='a';measure.rt.formula
    }

    $scope.clearRT = function() {
        $scope.copyRT=angular.copy($scope.rt.definition);
        $scope.rt.definition = null;
    }

    $scope.toggleHasSubMeasures = function(measure) {
        if ($scope.$root.questions) {
           //delete $scope.$root.questions;
        }
        measure.hasSubMeasures = !measure.hasSubMeasures;
        if(measure.hasSubMeasures) {
            //$scope.edit.model.rt.formula='a';
            if (!measure.rt)
               measure.rt=angular.copy($scope.rt);
            if ($scope.rt.definition)   
                measure.rt.name=$scope.rt.definition.name;
            if (!measure.subMeasures) measure.subMeasures = [];
            if (measure.subMeasures.length <= 0) {
                //measure.rt=angular.copy($scope.rt);
                //measure.rt.name=$scope.edit.model.responseType.name;
                //measure.rt.name=$scope.rt.definition.name;
                $scope.addSubMeasure(measure, angular.copy($scope.rt));
            }
            if ($scope.edit.model.responseType && $scope.edit.model.responseType.formula) {
                if ($scope.edit.model.rt) {
                    $scope.edit.model.rt.formula=$scope.edit.model.responseType.formula;
                }
                else {
                    $scope.edit.model.rt={formula:$scope.edit.model.responseType.formula};
                }
            }
        }
        else {
            $scope.rt.definition.name= measure.rt.name;
            if (measure.rt.id)
               $scope.rt.definition.id= measure.rt.id;
            else 
               $scope.rt.definition.id= measure.rt.definition.id;  
        }
    };


    $scope.removeSubMeasure = function(measure, subMeasure, index) {
        if ($rootScope.questions && $rootScope.questions[index]) {
            $rootScope.questions[index]={};
        }
        if ($rootScope.rts && $rootScope.rts[index]) {
            $rootScope.rts[index]={};
        }
        if (measure.subMeasures.length>1) 
        {
            measure.subMeasures.forEach(function(sm,i){
                if (!sm.deleted && index!=i ) {
                    return subMeasure.deleted=true;
                }
            })

        }
        if (!subMeasure.deleted)
           $scope.toggleHasSubMeasures(measure)
           

    }


    $scope.addSubMeasure = function(measure,rt) {

        if (!measure.subMeasures)  measure.subMeasures = [];
        var rtName=''
        if (rt && rt.definition) rtName=rt.definition.name;
        measure.subMeasures.push({
            name: rtName,
            description: '',
            responseTypeId: null,
            sourceVars: [],
            rt: rt || {
                definition:  null,
                responseType: null,
                search: {
                    programId: $scope.measure.programId,
                    pageSize: 5,
                }  
            }     
        });
        if ($rootScope.questions) {
            $rootScope.questions.push({})
        }
        else
        {
            $rootScope.questions=[{}]
        }
        if ($rootScope.rts) {
            $rootScope.rts.push({})
        }
        else
        {
            $rootScope.rts=[{}]
        }
    };

    $scope.newResponseType = function(type,index) {
        var parts;
        let defaultFormula='a';
        if (index) {
            defaultFormula='';
        }
        if (type == 'multiple_choice') {
            parts = [{type: 'multiple_choice', id: 'a', options: [
                {name: 'No', score: 0},
                {name: 'Yes', score: 1}]
            }];
        } else if (type == 'numerical') {
            parts = [{type: 'numerical', id: 'a'}];
        }
        return new ResponseType({
            obType: 'response_type',
            programId: $scope.edit.model.programId,
            name: $scope.edit.model.title,
            parts: parts,
            formula: defaultFormula,
        });
    };
    $scope.cloneResponseType = function() {
        var rtDef = angular.copy($scope.rt.definition)
        rtDef.id = null;
        rtDef.name = rtDef.name + ' (Copy)'
        rtDef.nMeasures = 0;
        return rtDef;
    };
    $scope.rt = {
        definition: routeData.responseType || null,
        responseType: null,
        search: {
            programId: $scope.measure.programId,
            pageSize: 5,
        },
    };

    if ($scope.submission) {
        // Get the response that is associated with this measure and submission.
        // Create an empty one if it doesn't exist yet.
        $scope.lastSavedResponse = null;
        $scope.setResponse = function(response) {
            if (!response.responseParts)
                response.responseParts = [];
            if ($scope.measure.hasSubMeasures) {
                response.subMeasures=$scope.measure.subMeasures;
            }
            $scope.model.response = response;
            $scope.lastSavedResponse = angular.copy(response);
        };

        var nullResponse = function(measure, submission) {
            return new Response({
                measureId: $scope.measure ? $scope.measure.id : null,
                subMeasures: $scope.measure.subMeasures ? $scope.measure.subMeasures:null,
                submissionId: $scope.submission ? $scope.submission.id : null,
                responseParts: [],
                comment: '',
                notRelevant: false,
                approval: 'draft'
            });
        };
        $scope.setResponse(nullResponse());
        Response.get({
            measureId: $scope.measure.id,
            submissionId: $scope.submission.id
        }).$promise.then(
            function success(response) {
                // should make response_parts change if response_type part type changed
                if (response.responseParts.length>0) {
                    angular.forEach($scope.rt.definition.parts, function(part,index){
                       if ((part.type=='multiple_choice' && response.responseParts[index].value) ||
                          (part.type=='numerical' && response.responseParts[index].index)) {
                           response.responseParts[index]={};
                        }
                    });
                }

                //end type changed
                $scope.setResponse(response);
            },
            function failure(details) {
                if (details.status != 404) {
                    Notifications.set('edit', 'error',
                        "Failed to get response details: " + details.statusText);
                    return;
                }
                $scope.setResponse(nullResponse(
                    $scope.measure, $scope.submission));
            }
        );

        var interceptingLocation = false;
        $scope.$on('$locationChangeStart', function(event, next, current) {
            if (!$scope.model.response.$dirty || interceptingLocation)
                return;
            event.preventDefault();
            interceptingLocation = true;
            $scope.saveResponse().then(
                function success() {
                    $window.location.href = next;
                    $timeout(function() {
                        interceptingLocation = false;
                    });
                },
                function failure(details) {
                    var message = "Failed to save: " +
                        details.statusText +
                        ". Are you sure you want to leave this page?";
                    var answer = confirm(message);
                    if (answer)
                        $window.location.href = next;
                    $timeout(function() {
                        interceptingLocation = false;
                    });
                }
            );
        });

        $scope.saveResponse = function() {
            return $scope.model.response.$save().then(
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
                });
        };
        $scope.resetResponse = function() {
            $scope.model.response = angular.copy($scope.lastSavedResponse);
        };
        $scope.toggleNotRelvant = function() {
            var oldValue = $scope.model.response.notRelevant;
            $scope.model.response.notRelevant = !oldValue;
            $scope.model.response.$save().then(
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                },
                function failure(details) {
                    if (details.status == 403) {
                        Notifications.set('edit', 'info',
                            "Not saved yet: " + details.statusText);
                        if (!$scope.model.response) {
                            $scope.setResponse(nullResponse(
                                $scope.measure, $scope.submission));
                        }
                    } else {
                        $scope.model.response.notRelevant = oldValue;
                        Notifications.set('edit', 'error',
                            "Could not save: " + details.statusText);
                    }
                });
        };
        $scope.setState = function(state) {
            $scope.model.response.$save({approval: state},
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save: " + details.statusText);
                }
            );
        };
        $scope.$watch('response', function() {
            $scope.model.response.$dirty = !angular.equals(
                $scope.model.response, $scope.lastSavedResponse);
        }, true);
    }

    $scope.$watch('measure', function(measure) {
        $scope.structure = Structure(measure, $scope.submission);
        $scope.program = $scope.structure.program;
        $scope.edit = Editor('measure', $scope, {
            parentId: measure.parent && measure.parent.id,
            surveyId: measure.parent && measure.parent.survey.id,
            programId: $scope.program.id
        });
        if (!measure.id) {
            $scope.edit.edit();
            //$scope.edit.model.rt.formula='a';
        }

        if (measure.parents) {
            var parents = [];
            for (var i = 0; i < measure.parents.length; i++) {
                parents.push(Structure(measure.parents[i]));
            }
            $scope.parents = parents;
        }
    });
    $scope.$watch('structure.program', function(program) {
        $scope.checkRole = Authz({
            program: $scope.program,
            submission: $scope.submission,
        });
        $scope.editable = ($scope.program.isEditable &&
            !$scope.structure.deletedItem &&
            !$scope.submission);
    });

    $scope.removeReponseType=function(index){
        if ($rootScope.questions && $rootScope.questions[index]) {
            $rootScope.questions[index]={};
        }
        if ($rootScope.rts && $rootScope.rts[index]) {
            $rootScope.rts[index]={};
        }
        //$scope.rt.definition=null;
    }


    var rtDefChanged = Enqueue(function() {
        var rtDef = $scope.rt.definition;
        if (!rtDef && !($scope.edit.model && $scope.edit.model.hasSubMeasures)) {           
            $scope.rt.responseType = null;
            //$scope.$broadcast("remove-responseType");
            return;
        }
        // has submeasure, use measure's formula
        if ($scope.edit.model && $scope.edit.model.hasSubMeasures) {
            var mergeParts=[];
            angular.forEach($rootScope.rts,function(rt,i){
                if (!angular.equals({}, rt)) {
                   mergeParts=[...mergeParts, ...rt.rtEdit.rt.parts]
                }
            });
            var merge={parts:mergeParts, formula:$scope.edit.model.rt.formula};
            $scope.rt.responseType = new responseTypes.ResponseType(
                "", merge.parts, $scope.edit.model.rt.formula);
            //set declaredVars freeVars unboundVars to current submeasure
            if ($rootScope.indexSub && $rootScope.rts && $rootScope.rts[$rootScope.indexSub].rtEdit 
                && $rootScope.rts[$rootScope.indexSub].rtEdit.responseType) {
               $rootScope.rts[$rootScope.indexSub].rtEdit.responseType.unboundVars=angular.copy($scope.rt.responseType.unboundVars);
               $rootScope.rts[$rootScope.indexSub].rtEdit.responseType.freeVars=angular.copy($scope.rt.responseType.freeVars);
               $rootScope.rts[$rootScope.indexSub].rtEdit.responseType.declaredVars=angular.copy($scope.rt.responseType.declaredVars);
            }
        }
        else { //no submeasure, 
            $scope.rt.responseType = new responseTypes.ResponseType(
               rtDef.name, rtDef.parts, rtDef.formula);
        }
        


        //put submeasure seq, description, comment, attachement to responseType
        /*var lastSubmeasureId=null;
        var subSeq=1;
        $scope.rt.responseType.parts.forEach(function(item,index){
            if (lastSubmeasureId!=item.submeasure) {
                if (lastSubmeasureId) {
                    $scope.rt.responseType.parts[index-1].comment="";
                }
                $scope.measure.subMeasures.forEach(function(sub,i){
                    if (sub.id==item.submeasure) {
                        item.subDesc=sub.description;
                        item.subSeq=subSeq;
                        subSeq=subSeq+1;
                    } 
                    lastSubmeasureId=item.submeasure;
                });

            }
        })
        $scope.rt.responseType.parts[$scope.rt.responseType.parts.length-1].comment="";*/

    }, 0, $scope);

    /*$scope.$watch('edit.model.rt.formula', function(){
        if ($scope.measure.subMeasures) {
            $scope.measure.subMeasures.forEach(function(sub,i){
                sub.rt.definition.formula=$scope.edit.model.rt.formula;
            }); 
        }

    });*/
    $scope.$on('response-type-changed',rtDefChanged);
    $scope.$watch('rt.definition', rtDefChanged);
    $scope.$watch('rt.definition', rtDefChanged, true);
    $scope.$watchGroup(['rt.responseType', 'edit.model'], function(vars) {
        var responseType = vars[0],
            measure = vars[1];
        if (!responseType || !measure || !measure.sourceVars) {
            // A measure only has source variables when viewed in the context
            // of a survey.
            return;
        }
        var measureVariables = measure.sourceVars.filter(
            function(measureVariable) {
                // Remove bindings that have not been set yet
                return measureVariable.sourceMeasure;
            }
        );
        measureVariables.forEach(function(measureVariable) {
            measureVariable.$unused = true;
        });
        responseType.unboundVars.forEach(function(targetField) {
            var measureVariable;
            for (var i = 0; i < measureVariables.length; i++) {
                var mv = measureVariables[i];
                if (mv.targetField == targetField) {
                    mv.$unused = false;
                    return;
                }
            }
            measureVariables.push({
                targetField: targetField,
                sourceMeasure: null,
                sourceField: null,
            });
        });
        measureVariables.sort(function(a, b) {
            return a.targetField.localeCompare(b);
        });
        measure.sourceVars = measureVariables;
    });
    $scope.searchMeasuresToBind = function(term) {
        return Measure.query({
            term: term,
            programId: $scope.structure.program.id,
            surveyId: $scope.structure.survey.id,
            withDeclaredVariables: true,
        }).$promise;
    };

    var applyRtSearch = Enqueue(function() {
        if (!$scope.rt.showSearch)
            return;
        ResponseType.query($scope.rt.search).$promise.then(
            function success(rtDefs) {
                $scope.rt.searchRts = rtDefs;
                /*if (!$scope.subIndex && $scope.subIndex!=0) {
                    // if select in measure level
                    $scope.rt.searchRts = rtDefs;
                }
                else {
                    // if select in submeasure level, get submeasure parts
                    var currentSubmeasres=0; // submeasres number in target measure 
                    var rtSubmeasures=0;  // submeasres number in source measure 
                    var preSubmeasure=null;
                    var sourceSubmeasure=[]
                    var partObject=null;
                    

                    var rtSubDefs=[];
                    angular.forEach(rtDefs,function(resolvedRtDef){
                        var targetRtDef=angular.copy(resolvedRtDef);
                        angular.forEach(resolvedRtDef.parts,function(item){
                            if (item.type == 'multiple_choice') {
                                partObject=new responseTypes.MultipleChoice(item);
                            }
                            else if (item.type == 'numerical') {
                                partObject=new responseTypes.Numerical(item);
                            } 
                            partObject.submeasure= item.submeasure; 
                            var itemCopy=angular.copy(item);
                                
                            if (preSubmeasure != item.submeasure) {
                                rtSubmeasures=rtSubmeasures+1;
                                sourceSubmeasure.push({ 
                                    id:item.submeasure,
                                    description: item.description,
                                    rt: {
                                        definition:{
                                            parts:[itemCopy],
                                            name:item.name,
                                        },
                                        responseType: resolvedRtDef || null ,
                                        search: {
                                          programId: $scope.measure.programId,
                                          pageSize: 5,
                                        } 
                                    },
                                    rtRead:{
                                        definition:{
                                            parts:[partObject],
                                            name:item.title
                                        }
                                    },
                                    name: item.title,
                               })
        
                            }
                            else
                            {
                                sourceSubmeasure[rtSubmeasures-1].rt.definition.parts.push(itemCopy);
                                sourceSubmeasure[rtSubmeasures-1].rtRead.definition.parts.push(partObject);
                                
                            }
        
                            preSubmeasure=item.submeasure;
                        });                           
                    });






                    $scope.rt.searchRts = rtDefs;
                } */
            },
            function failure(details) {
                Notifications.set('measure', 'error',
                    "Could not get response type list: " + details.statusText);
            }
        );
    }, 100, $scope);

    /*var applyRtSearchForSubmeasure = Enqueue(function() {
        if (!$scope.edit.model || !$scope.edit.model.subMeasures[$scope.subIndex].rt.showSearch || (!$scope.subIndex && $scope.subIndex!=0))
            return;
        ResponseType.query($scope.measure.subMeasures[$scope.subIndex].rt.search).$promise.then(
            function success(rtDefs) {
                if (!$scope.subIndex || $scope.subIndex!=0)
                   $scope.measure.subMeasures[$scope.subIndex].rt.searchRts = rtDefs;
                else {
                    $scope.measure.subMeasures[$scope.subIndex].rt.searchRts =[];
                }   
            },
            function failure(details) {
                Notifications.set('measure', 'error',
                    "Could not get response type list: " + details.statusText);
            }
        );
    }, 100, $scope);*/

    $scope.setSubIndex=function(i) {
        $scope.rt.search.term="";
        $scope.subIndex=i;
    }

    $scope.setLinkOrCopy=function(op) {
        $scope.rt.search.term="";
        $scope.op=op;
    }

    $scope.$watch('rt.search', applyRtSearch, true);
    $scope.$watch('rt.showSearch', applyRtSearch, true);
    //$scope.$watchCollection(()=>($scope.measure.subMeasures.filter(sm=>sm.rt.search!=undefined).map(sm=>sm.rt.search)), applyRtSearchForSubmeasure, true);
    //$scope.$watchCollection('measure.subMeasures', applyRtSearchForSubmeasure, true);
    /*angular.forEach($scope.measure.subMeasures,function(item,index){
        $scope.$watch('edit.model.subMeasures['+index+'].rt.search', applyRtSearchForSubmeasure, true);
    })*/

    $scope.chooseResponseTypeForSubmeasure = function(rtDef) {
         if ($scope.subIndex >= 0) {
            angular.forEach(rtDef.parts, function(p){
                p.submeasure=$scope.edit.model.subMeasures[$scope.subIndex].id;
            })
            if ($scope.edit.model.subMeasures[$scope.subIndex].rt.definition) {
                //exist submeasure
                $scope.edit.model.subMeasures[$scope.subIndex].rt.definition.parts=angular.copy(rtDef.parts);
            }
            else {
                //new submeasure
                $scope.edit.model.subMeasures[$scope.subIndex].rt.definition={parts:angular.copy(rtDef.parts)};
            }   
            if (!$scope.edit.model.subMeasures[$scope.subIndex].rt.definition.name || 
                $scope.edit.model.subMeasures[$scope.subIndex].rt.definition.name.trim().length==0 )
                $scope.edit.model.subMeasures[$scope.subIndex].rt.definition.name=rtDef.name;

         }
         $scope.rt.showSearch = false;
    }
    $scope.copyResponseType = function(rtDef) {
        ResponseType.get(rtDef, {
            programId: $scope.structure.program.id
        }).$promise.then(function(resolvedRtDef) {
            if ($scope.edit.model.hasSubMeasures && resolvedRtDef && resolvedRtDef.parts[0].submeasure) {
                //convert submeasure repsonse-type parts
                var currentSubmeasres=0; // submeasres number in target measure 
                var rtSubmeasures=0;  // submeasres number in source measure 
                var preSubmeasure=null;
                var sourceSubmeasure=[]
                var partObject=null;
                var targetRtDef=angular.copy(resolvedRtDef);
                angular.forEach(resolvedRtDef.parts,function(item){
                    if (item.type == 'multiple_choice') {
                        partObject=new responseTypes.MultipleChoice(item);
                    }
                    else if (item.type == 'numerical') {
                        partObject=new responseTypes.Numerical(item);
                    } 
                    partObject.submeasure= item.submeasure; 
                    var itemCopy=angular.copy(item);
                    if (preSubmeasure != item.submeasure) {
                        rtSubmeasures=rtSubmeasures+1;
                        sourceSubmeasure.push({ 
                            id:item.submeasure,
                            description: item.description,
                            rt: {
                                definition:{
                                    parts:[itemCopy],
                                    name:item.name,
                                },
                                responseType: resolvedRtDef || null ,
                                search: {
                                  programId: $scope.measure.programId,
                                  pageSize: 5,
                                } 
                            },
                            //rtRead:{
                            //    definition:{
                            //        parts:[partObject],
                            //        name:item.title
                            //    }
                            //},
                            name: item.title,
                       })
                    }
                    else
                    {
                        sourceSubmeasure[rtSubmeasures-1].rt.definition.parts.push(itemCopy);
                        //sourceSubmeasure[rtSubmeasures-1].rtRead.definition.parts.push(partObject);
                    }
                    preSubmeasure=item.submeasure;
                });
                var subMeasures=[];
                var partObject=null;
                if ($scope.measure.subMeasures.length<=rtSubmeasures) {
                    angular.forEach(sourceSubmeasure,function(item,index){
                        if (index < $scope.measure.subMeasures.length) {
                            angular.forEach(item.rt.definition.parts,function(part) {
                                part.submeasure=$scope.measure.subMeasures[index].id;
                            });
                            //angular.forEach(item.rtRead.definition.parts,function(part) {
                            //    part.submeasure=$scope.measure.subMeasures[index].id;
                            //});
                            subMeasures.push({ 
                                id: $scope.measure.subMeasures[index].id,
                                description: $scope.measure.subMeasures[index].description,
                                rt:{
                                    definition:{
                                        parts:item.rt.definition.parts,
                                        name:$scope.measure.subMeasures[index].name
                                    },
                                    responseType: resolvedRtDef || null,
                                    search: {
                                        programId: $scope.measure.programId,
                                        pageSize: 5,
                                    }  
                                },
                                /*rtRead:{ 
                                    definition:{
                                        parts:item.rtRead.definition.parts,
                                        name:$scope.measure.subMeasures[index].name,
                                    }
                                },*/
                                name: $scope.measure.subMeasures[index].name,                         
                            });
                        }
                        else {
                            angular.forEach(item.rt.definition.parts,function(part) {
                                delete part.submeasure;
                            });
                            //angular.forEach(item.rtRead.definition.parts,function(part) {
                            //    delete part.submeasure;
                            //});
                            subMeasures.push({ 
                                // id: $scope.measure.subMeasures[index].id,
                                //description: $scope.measure.subMeasures[index].description,
                                rt:{
                                    definition:{
                                        parts:item.rt.definition.parts,
                                        name:item.name
                                    },
                                    responseType: resolvedRtDef || null,
                                            
                                    search: {
                                        programId: $scope.measure.programId,
                                        pageSize: 5,
                                           
                                    }  
                                       
                                },
                                /*rtRead:{ 
                                    definition:{
                                        parts:item.rtRead.definition.parts,
                                        name:item.name,
                                    }
                                },*/
                                name: item.name,                         
                            });

                            if ($rootScope.questions) {
                                $rootScope.questions.push({})
                            }
                            else
                            {
                                $rootScope.questions=[{}]
                            }
                            if ($rootScope.rts) {
                                $rootScope.rts.push({})
                            }
                            else
                            {
                                $rootScope.rts=[{}]
                            }
                        }
                    });
                    $scope.edit.model.rt.parts=angular.copy(resolvedRtDef.parts);
                    $scope.edit.model.rt.formula=resolvedRtDef.formula;
                    $scope.edit.model.subMeasures=angular.copy(subMeasures);
                    $scope.rt.definition = resolvedRtDef;
                }
                else {
                    Notifications.set('edit', 'error',
                    "Could not copy: "+ "Submeasures in another measure should be more than the submeasure number of current measure");
                }

            }
            else if ($scope.edit.model.hasSubMeasures && resolvedRtDef && (!resolvedRtDef.parts[0].submeasure)) {
                Notifications.set('edit', 'error',
                "Could not copy: "+ "Submeasures in another measure should be more than the submeasure number of current measure");
            }
            else { 
                // if edit measure  without submeasure and copy response type, response type name not change
                // $scope.measure.responseType keep responseType data before change for recover when cancel edit 
                if ($scope.rt.definition && $scope.rt.responseType && $scope.measure.id) {
                    resolvedRtDef.name=$scope.measure.responseType.name;
                    resolvedRtDef.id=$scope.rt.definition.id;
                }
                $scope.rt.definition = angular.copy(resolvedRtDef);
                //$scope.rt.definition.id = null;
                // if edit measure without submeasure, response type name not change
                // if add measure without submeasure, response type name change depend on copy response type name
                //if (!$scope.edit.model.rt.name || $scope.edit.model.rt.name.trim().length==0 || !$scope.measure.id) {
                if (!$scope.measure.id) {
                   $scope.rt.definition.name = $scope.rt.definition.name + ' (Copy)';
                   $scope.rt.definition.id = null;
                }
                $scope.rt.definition.nMeasures = 0;

            }
        });
        
        $scope.rt.showSearch = false;
    };

    $scope.chooseResponseType = function(rtDef) {
        ResponseType.get(rtDef, {
            programId: $scope.structure.program.id
        }).$promise.then(function(resolvedRtDef) {
            if ($scope.edit.model.hasSubMeasures && resolvedRtDef && resolvedRtDef.parts[0].submeasure) {
                //convert submeasure repsonse-type parts


                var currentSubmeasres=0; // submeasres number in target measure 
                var rtSubmeasures=0;  // submeasres number in source measure 
                var preSubmeasure=null;
                var sourceSubmeasure=[]
                var partObject=null;
                var targetRtDef=angular.copy(resolvedRtDef);
                angular.forEach(resolvedRtDef.parts,function(item){
                    if (item.type == 'multiple_choice') {
                        partObject=new responseTypes.MultipleChoice(item);
                    }
                    else if (item.type == 'numerical') {
                        partObject=new responseTypes.Numerical(item);
                    } 
                    partObject.submeasure= item.submeasure; 
                    var itemCopy=angular.copy(item);
                        
                    if (preSubmeasure != item.submeasure) {
                        rtSubmeasures=rtSubmeasures+1;
                        sourceSubmeasure.push({ 
                            id:item.submeasure,
                            description: item.description,
                            rt: {
                                definition:{
                                    parts:[itemCopy],
                                    name:item.name,
                                },
                                responseType: targetRtDef || null ,
                                search: {
                                  programId: $scope.measure.programId,
                                  pageSize: 5,
                                } 
                            },
                            /*rtRead:{
                                definition:{
                                    parts:[partObject],
                                    name:item.name
                                }
                            },*/
                            name: item.name,
                       })

                    }
                    else
                    {
                        sourceSubmeasure[rtSubmeasures-1].rt.definition.parts.push(itemCopy);
                        //sourceSubmeasure[rtSubmeasures-1].rtRead.definition.parts.push(partObject);
                        
                    }

                    preSubmeasure=item.submeasure;
                });

                var subMeasures=[];
                var partObject=null;
                var rtName='';
                //if (!$scope.measure.subMeasures) {
                //    $scope.measure.subMeasures=angular.copy($scope.edit.model.subMeasures);
                //}
                if ($scope.edit.model.subMeasures.length<=rtSubmeasures) {
                    angular.forEach(sourceSubmeasure,function(item,index){
                        //if (index==0) {
                        //    rtName=item.name +" (copy)";
                        //}
                        //else {
                            rtName= item.name ;
                        //}
                        if (index < $scope.edit.model.subMeasures.length) {
                            angular.forEach(item.rt.definition.parts,function(part) {
                                part.submeasure=$scope.edit.model.subMeasures[index].id;
                            });
                            //angular.forEach(item.rtRead.definition.parts,function(part) {
                            //    part.submeasure=$scope.edit.model.subMeasures[index].id;
                            //});

                               
                            subMeasures.push({ 
                                id: $scope.edit.model.subMeasures[index].id,
                                description: $scope.edit.model.subMeasures[index].description,
                                rt:{
                                    definition:{
                                        parts: item.rt.definition.parts,
                                        name: $scope.edit.model.subMeasures[index].name
                                    },
                                    responseType: targetRtDef || null,
                                            
                                    search: {
                                        programId: $scope.edit.model.programId,
                                        pageSize: 5,
                                           
                                    }  
                                       
                                },
                                /*rtRead:{ 
                                    definition:{
                                        parts:item.rtRead.definition.parts,
                                        name:$scope.edit.model.subMeasures[index].name,
                                    }
                                },*/
                                name: $scope.edit.model.subMeasures[index].name,                         
                            });
                        }
                        else {
                            angular.forEach(item.rt.definition.parts,function(part) {
                                delete part.submeasure;
                            });
                            //angular.forEach(item.rtRead.definition.parts,function(part) {
                            //    delete part.submeasure;
                            //});
                            subMeasures.push({ 
                                // id: $scope.measure.subMeasures[index].id,
                                //description: $scope.measure.subMeasures[index].description,
                                rt:{
                                    definition:{
                                        parts:item.rt.definition.parts,
                                        name:rtName // item.name
                                    },
                                    responseType: targetRtDef || null,
                                            
                                    search: {
                                        programId: $scope.measure.programId,
                                        pageSize: 5,
                                           
                                    }  
                                       
                                },
                                /*rtRead:{ 
                                    definition:{
                                        parts:item.rtRead.definition.parts,
                                        name:item.name,
                                    }
                                },*/
                                name: item.name,                         
                            });

                            if ($rootScope.questions) {
                                $rootScope.questions.push({})
                            }
                            else
                            {
                                $rootScope.questions=[{}]
                            }
                            if ($rootScope.rts) {
                                $rootScope.rts.push({})
                            }
                            else
                            {
                                $rootScope.rts=[{}]
                            }




                        }




                    });



                



                /*angular.forEach($scope.measure.subMeasures,function(item){
                    if (!angular.equals({}, item)) {
                        currentSubmeasres=currentSubmeasres+1;
                    }
                }*/
                /*--var submeasure_id=[];
                
                if ($scope.measure.subMeasures.length<=rtSubmeasures) {
                    resolvedRtDef.name=$scope.measure.title;
                    preSubmeasure=null;
                    var currentSubmeasureIndex=-1;
                    angular.forEach(resolvedRtDef.parts,function(item,index){
                        if (preSubmeasure != item.submeasure) {
                            currentSubmeasureIndex=currentSubmeasureIndex+1;
                        }
                        if (currentSubmeasureIndex<$scope.measure.subMeasures.length) {
                            item.submeasure=$scope.measure.subMeasures[currentSubmeasureIndex].id;
                            submeasure_id.push($scope.measure.subMeasures[currentSubmeasureIndex].id);
                        }--*/
                        /*else {
                            delete item.submeasure;

                            if ($rootScope.questions) {
                                $rootScope.questions.push({})
                            }
                            else
                            {
                                $rootScope.questions=[{}]
                            }
                            if ($rootScope.rts) {
                                $rootScope.rts.push({})
                            }
                            else
                            {
                                $rootScope.rts=[{}]
                            }
                        }*/

                    /*--    preSubmeasure=item.submeasure;
                    });

                    var subMeasures=[];
                    var partObject=null;
                    
                    angular.forEach(resolvedRtDef.parts,function(item,index){
                        if (item.type == 'multiple_choice') {
                            partObject=new responseTypes.MultipleChoice(item);
                        }
                        else if (item.type == 'numerical') {
                            partObject=new responseTypes.Numerical(item);
                        } 
                        partObject.submeasure= item['submeasure']; 
                        
                        if (subMeasures.length==0) {
                           $scope.measure.subMeasureList.forEach(function(sub,i){
                                if (sub.id==item.submeasure) {
                                    subMeasures.push({ id:item['submeasure'],
                                        description: sub['description'],
                                        rt:{
                                            definition:{parts:[item],name:sub.title},
                                            responseType: resolvedRtDef || null,
                                            search: {
                                                programId: $scope.measure.programId,
                                                pageSize: 5,
                                            }  
                                        },
                                        'rtRead':{'definition':{'parts':[partObject],'name':sub['title']}},
                                        'name': sub['title'],                         
                                    });
                                }
                       
                            });
                        }
                        else
                        {
                            var notFoundSubmeasure=true;
                            angular.forEach(subMeasures,function(s,i){
                                if (s.id==item['submeasure']){   
                                    s.rt.definition.parts.push(item);
                                    s.rtRead.definition.parts.push(partObject);
                                    notFoundSubmeasure=false;
                                }
    
                            });
                            if (notFoundSubmeasure) {
                                $scope.measure.subMeasureList.forEach(function(sub,i){
                                    if (sub.id==item.submeasure) {
                                        subMeasures.push({ 'id':item['submeasure'],
                                        'description': sub['description'],
                                        'rt':{
                                                'definition':{'parts':[item],'name':sub['title']},
                                                'responseType': resolvedRtDef || null ,
                                                search: {
                                                  programId: $scope.measure.programId,
                                                  pageSize: 5,
                                                } 
                                        },
                                        'rtRead':{'definition':{'parts':[partObject],'name':sub['title']}},
                                        'name': sub['title'],
                                       })
                                    }
                               
                                });     --*/                       
                                /*subMeasures.push({ 'id':item['submeasure'],
                                      'description':item['description'],
                                      'rt':{'definition':{'parts':[item]}}
                                })*/
                           /*-- }
                        }
                    });--*/
                    //$scope.measure['subMeasures']=angular.copy(subMeasures);
                    $scope.edit.model.rt.parts=angular.copy(resolvedRtDef.parts);
                    $scope.edit.model.rt.formula=resolvedRtDef.formula;
                    // if edit measure with submeasure, response type name not change
                    // if add measure with submeasure, response type name change depend on copy response type name
                    if (!$scope.edit.model.rt.name || $scope.edit.model.rt.name.trim().length==0 || !$scope.measure.id)
                       $scope.edit.model.rt.name=resolvedRtDef.name +" (copy)";
                    $scope.edit.model.subMeasures=angular.copy(subMeasures);
                    $scope.rt.definition = angular.copy(resolvedRtDef);
                }
                else {
                    Notifications.set('edit', 'error',
                    "Could not copy: "+ "Submeasures in another measure should be more than the submeasure number of current measure");
                }

            }
            else if ($scope.edit.model.hasSubMeasures && resolvedRtDef && (!resolvedRtDef.parts[0].submeasure)) {
                Notifications.set('edit', 'error',
                "Could not copy: "+ "Submeasures in another measure should be more than the submeasure number of current measure");
            }
            else {
                $scope.rt.definition = resolvedRtDef;
            }
        });
        
        $scope.rt.showSearch = false;
    };

    $scope.save = function() {
        /*if ($rootScope.questions) {
            delete $rootScope.questions;
        }
        if ($rootScope.rts) {
            delete $rootScope.rts;
        }
        if ($rootScope.externs) {
            delete $rootScope.externs;
        }
        if ($rootScope.indexSub) {
            delete $rootScope.indexSub;
        }  */
        if (!$scope.edit.model)
            return;
         

        if (!$scope.rt.definition && !$scope.edit.model.hasSubMeasures) {
            Notifications.set('edit', 'error',
                "Could not save: No repsonse type");
            return;
        }
        $scope.edit.model.has_sub_measures=$scope.edit.model.hasSubMeasures;
        if ($scope.edit.model.sourceVars) {
            $scope.edit.model.sourceVars = $scope.edit.model.sourceVars.filter(function(mv) {
                return !mv.$unused;
             });
         }

        if ($scope.edit.model.hasSubMeasures) {
            //if (!$scope.edit.model.rt.name)
            if ($scope.edit.model.subMeasures && $scope.edit.model.subMeasures.length>0 
                && $scope.edit.model.subMeasures[0].rt.definition && !$scope.rt.definition) {
                 $scope.rt.definition=angular.copy($scope.edit.model.subMeasures[0].rt.definition);
            }
            if (!$scope.rt.definition) {
                Notifications.set('edit', 'error',
                    "Could not save: No repsonse type");
                return;
            }
            if (!$scope.edit.model.rt.parts)
            {
                $scope.edit.model.rt.parts= [];
            }
            let error="";
            angular.forEach($scope.edit.model.subMeasures,function(item,index){
                if (item.deleted != true) {
                    if (item.rt.definition) {
                        if (item.rt.definition.name && item.rt.definition.name!="") {
                            item.title=item.rt.definition.name;
                            item.weight=$scope.edit.model.weight;
                        }
                        else {
                            error="Name is empty";
                        }
                    }
                    else {
                    // one of submeasure no response type, measure no response type
                         error="Submeasure "+ (index + 1) +" no repsonse type";
                    }
                }
            })
            if (error!="") {
                Notifications.set('edit', 'error',
                    "Could not save: "+ error);
                return;
            }
            //$scope.edit.model.rt.name=$scope.edit.model.subMeasures[0].rt.definition.name;
            return $scope.edit.save();
        }
        else {
            if ( !$scope.edit.model.title || $scope.edit.model.title.trim().length == 0) {
                Notifications.set('edit', 'error',"Could not save: Name is empty");
                return;

            }
            $scope.rt.definition.parts.forEach(function(part) {
                if (part.submeasure) {
                   delete part.submeasure;
                }
            });
            $scope.rt.definition.$createOrSave().then(
                function success(definition) {
                    var measure = $scope.edit.model;
                    if (measure.sourceVars) {
                       measure.sourceVars = measure.sourceVars.filter(function(mv) {
                           return !mv.$unused;
                        });
                    }
                    measure.responseTypeId = definition.id;
                    return $scope.edit.save();
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save: " + details.statusText);
                }
            );
        }
    };
    $scope.$on('EditSaved', function(event, model) {
        $location.url($scope.getUrl(model));
        /*if ($rootScope.questions) {
            delete $rootScope.questions;
        }
        if ($rootScope.rts) {
            delete $rootScope.rts;
        }
        if ($rootScope.externs) {
            delete $rootScope.externs;
        }
        if ($rootScope.indexSub) {
            delete $rootScope.indexSub;
        }  
        if (model.subMeasureList) {
            model.subMeasureList.forEach(function(sub,i){
                if ($rootScope.questions) {
                    $rootScope.questions.push({})
                }
                else
                {
                    $rootScope.questions=[{}]
                }
                if ($rootScope.rts) {
                    $rootScope.rts.push({})
                }
                else
                {
                    $rootScope.rts=[{}]
                }
            });
        }*/
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/3/qnode/{}?program={}', model.parent.id, model.programId));
        } else {
            $location.url(format(
                '/3/measures?program={}', model.programId));
        }
    });

    $scope.$on('saveResponse', $scope.saveResponse);

    $scope.Measure = Measure;

    if ($scope.submission) {
        var t_approval;
        if (currentUser.role == 'clerk' || currentUser.role == 'org_admin')
            t_approval = 'final';
        else if (currentUser.role == 'consultant')
            t_approval = 'reviewed';
        else
            t_approval = 'approved';
        hotkeys.bindTo($scope)
            .add({
                combo: ['ctrl+enter'],
                description: "Save the response, and mark it as " + t_approval,
                callback: function(event, hotkey) {
                    $scope.setState(t_approval);
                }
            });
    }

    $scope.getUrl = function(measure) {
        if ($scope.structure.submission) {
            return format('/3/measure/{}?submission={}',
                measure.id, $scope.structure.submission.id);
        } else {
            return format('/3/measure/{}?program={}&survey={}',
                measure.id, $scope.structure.program.id,
                $scope.structure.survey && $scope.structure.survey.id || '');
        }
    };

    $scope.getSubmissionUrl = function(submission) {
        if (submission) {
            /* in submeasure function response should be depend on the parent of measures
               should not anwser question per meausre */
            //return format('/3/measure/{}?submission={}',
            //    $scope.measure.id, submission.id,
            //$scope.parent && $scope.parent.id || '');
            return format('/3/qnode/{}?submission={}',
                $scope.measure.parent.id , submission.id,
                $scope.parent && $scope.parent.id || '');
        } else {
            return format('/3/measure/{}?program={}&survey={}',
                $scope.measure.id, $scope.structure.program.id,
                $scope.structure.survey && $scope.structure.survey.id || '');
        }
    };

    $scope.setRootScope=function(model){
        if ($rootScope.questions) {
            delete $rootScope.questions;
        }
        if ($rootScope.rts) {
            delete $rootScope.rts;
        }
        if ($rootScope.externs) {
            delete $rootScope.externs;
        }
        if ($rootScope.indexSub) {
            delete $rootScope.indexSub;
        }  
        //if ($scope.measure.subMeasureList.forEach) {
        //    $scope.measure.subMeasureList.forEach.forEach(function(sub,i){
        if (model.subMeasureList) {
            model.subMeasureList.forEach(function(sub,i){
                if ($rootScope.questions) {
                    $rootScope.questions.push({})
                }
                else
                {
                    $rootScope.questions=[{}]
                }
                if ($rootScope.rts) {
                    $rootScope.rts.push({})
                }
                else
                {
                    $rootScope.rts=[{}]
                }
            });
        }


    }


    /*$scope.checkSubMeasure=function(){
        if (routeData.responseType)
        {
           if (routeData.responseType.parts.length>0 && routeData.responseType.parts[0]['submeasure']){
               return true;
           }

        }
        else {
            return false;
        }
    };*/
})


.controller('MeasureLinkCtrl', function(
        $scope, QuestionNode, routeData, Authz,
        $location, Notifications, format,
        Measure, layout) {

    $scope.layout = layout;
    $scope.qnode = routeData.parent;
    $scope.program = routeData.program;

    $scope.measure = {
        parent: $scope.qnode,
        responseType: "dummy"
    };

    $scope.select = function(measure) {
        // postData is empty: we don't want to update the contents of the
        // measure; just its links to parents (giving in query string).
        var postData = {};
        Measure.save({
            id: measure.id,
            parentId: $scope.qnode.id,
            programId: $scope.program.id
        }, postData,
            function success(measure, headers) {
                var message = "Saved";
                if (headers('Operation-Details'))
                    message += ': ' + headers('Operation-Details');
                Notifications.set('edit', 'success', message);
                $location.url(format(
                    '/3/qnode/{}?program={}', $scope.qnode.id, $scope.program.id));
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
            }
        );
    };

    $scope.search = {
        term: "",
        programId: $scope.program.id,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Measure.query(search).$promise.then(function(measures) {
            $scope.measures = measures;
        });
    }, true);

    $scope.checkRole = Authz({program: $scope.program});
    $scope.QuestionNode = QuestionNode;
    $scope.Measure = Measure;
})


.controller('MeasureListCtrl', function(
        $scope, Authz, Measure, layout, routeData, $routeParams) {

    $scope.layout = layout;
    $scope.checkRole = Authz({});
    $scope.program = routeData.program;

    $scope.search = {
        term: $routeParams.initialTerm || "",
        programId: $scope.program && $scope.program.id,
        orphan: null,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Measure.query(search).$promise.then(function(measures) {
            $scope.measures = measures;
        });
    }, true);

    $scope.cycleOrphan = function() {
        switch ($scope.search.orphan) {
            case true:
                $scope.search.orphan = null;
                break;
            case null:
                $scope.search.orphan = false;
                break;
            case false:
                $scope.search.orphan = true;
                break;
        }
    };


})


;
