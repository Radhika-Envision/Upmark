'use strict';

angular.module('wsaa.response', ['ngResource', 'wsaa.admin'])


.factory('responseTypes', function() {
    // These classes are used to calculate scores and validate entered data.
    // They should be kept in sync with the classes on the server; see
    // response_type.py.

    function ResponseType(rtDef) {
        this.id = rtDef.id;
        this.name = rtDef.name;
        this.parts = rtDef.parts && rtDef.parts.map(responsePart) || [];
        this.formula = rtDef.formula ? Parser.parse(rtDef.formula) : null;
    };
    ResponseType.prototype.zip = function(responseParts) {
        var partPairs = [];
        for (var i = 0; i < this.parts.length; i++) {
            partPairs.push({
                index: i,
                schema: this.parts[i],
                data: responseParts[i],
            });
        }
        return partPairs;
    };
    ResponseType.prototype.score = function(responseParts, scope) {
        if (this.formula)
            return this.formula.evaluate(scope);

        var score = 0.0;
        this.zip(responseParts).forEach(function(part) {
            score += part.schema.score(part.data);
        });
        return score;
    };
    ResponseType.prototype.variables = function(responseParts, ignoreErrors) {
        var scope = {};
        this.zip(responseParts).forEach(function(part) {
            var vars;
            try {
                vars = part.schema.variables(part.data);
            } catch (e) {
                if (!ignoreErrors)
                    throw e;
            }
            angular.merge(scope, vars);
        });
        return scope;
    };
    ResponseType.prototype.validate = function(responseParts, scope) {
        this.zip(responseParts).forEach(function(part) {
            part.schema.validate(part.data, scope);
        });
    };
    ResponseType.prototype.calculate_score = function(responseParts) {
        if (!responseParts || responseParts.length != this.parts.length)
            throw "Response is incomplete.";

        var scope = this.variables(responseParts);
        this.validate(responseParts, scope);
        return this.score(responseParts, scope);
    };


    function responsePart(pDef) {
        if (pDef.options)
            return new MultipleChoice(pDef);
        else
            return new Numerical(pDef);
    };


    function ResponsePart(pDef) {
        this.id = pDef.id;
        this.name = pDef.name;
        this.type = pDef.type;
        this.description = pDef.description;
    };


    function MultipleChoice(pDef) {
        ResponsePart.call(this, pDef);
        this.options = pDef.options.map(function(oDef) {
            return new ResponseOption(oDef);
        });
    };
    MultipleChoice.prototype = Object.create(ResponsePart.prototype);
    MultipleChoice.prototype.score = function(part) {
        var option = this.options[part.index];
        return option.score;
    };
    MultipleChoice.prototype.variables = function(part) {
        var variables = {};
        if (this.id) {
            variables[this.id] = this.options[part.index].score;
            variables[this.id + '__i'] = part.index;
        }
        return variables;
    };
    MultipleChoice.prototype.validate = function(part, scope) {
        var option = this.options[part.index];
        if (!option.available(scope))
            throw "Conditions for option " + option.name + " are not met";
    };


    function ResponseOption(oDef) {
        this.score = oDef.score;
        this.name = oDef.name;
        this.description = oDef.description;
        this.predicate = oDef['if'] ? Parser.parse(oDef['if']) : null;
    };
    ResponseOption.prototype.available = function(scope) {
        if (!this.predicate)
            return true;
        try {
            return Boolean(this.predicate.evaluate(scope));
        } catch (e) {
            return false;
        }
    };


    function Numerical(pDef) {
        ResponsePart.call(this, pDef);
        this.lowerExp = pDef.lower ? Parser.parse(pDef.lower) : null;
        this.upperExp = pDef.upper ? Parser.parse(pDef.upper) : null;
    };
    Numerical.prototype = Object.create(ResponsePart.prototype);
    Numerical.prototype.score = function(part) {
        return part.value;
    };
    Numerical.prototype.variables = function(part) {
        var variables = {};
        if (this.id)
            variables[this.id] = part.value;
        return variables;
    };
    Numerical.prototype.lower = function(scope) {
        if (!this.lowerExp)
            return Number.NEGATIVE_INFINITY;
        return this.lowerExp.evaluate(scope);
    };
    Numerical.prototype.upper = function(scope) {
        if (!this.upperExp)
            return Number.POSITIVE_INFINITY;
        return this.upperExp.evaluate(scope);
    };
    Numerical.prototype.validate = function(part, scope) {
        var score = this.score(part);
        if (this.lower(scope) > score)
            throw "Must be greater than " + lower;
        if (this.upper(scope) < score)
            throw "Must be less than " + upper;
    };

    return {
        ResponseType: ResponseType,
        MultipleChoice: MultipleChoice,
        Numerical: Numerical,
    };
})


.directive('response', function(responseTypes) {
    console.log('response')
    return {
        restrict: 'E',
        scope: {
            responseType: '=type',
            model: '=model',
            weight_: '=weight',
            readonly: '=',
            hasQuality: '='
        },
        replace: true,
        templateUrl: 'response.html',
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Current', 'questionAuthz',
                'Notifications', 'Enqueue',
                function($scope, hotkeys, current, authz, Notifications,
                    Enqueue) {
            $scope.$watch('model', function(model) {
                if (model) {
                    $scope.response = model;
                } else {
                    $scope.response = {
                        responseParts: [],
                        comment: ''
                    };
                }
            });
            $scope.$watch('weight_', function(weight) {
                $scope.weight = weight == null ? 100 : weight;
            });

            $scope.$watch('responseType', function(rtDef) {
                $scope.rt = new responseTypes.ResponseType(rtDef);
            }, true);

            $scope.state = {
                partPairs: null,
                variables: null,
                score: 0,
                active: 0
            };

            var recalculate = Enqueue(function() {
                var rt = $scope.rt,
                    partsR = $scope.response.responseParts;
                rt.parts.forEach(function(part, i) {
                    if (!partsR[i])
                        partsR[i] = {};
                });
                $scope.state.partPairs = rt.zip(partsR);

                if ($scope.response.notRelevant) {
                    $scope.state.variables = {};
                    $scope.state.score = 0;
                } else {
                    $scope.state.variables = rt.variables(partsR, true);
                    try {
                        $scope.state.score = rt.score(
                            partsR, $scope.state.variables);
                        rt.validate(partsR, $scope.state.variables);
                        $scope.state.message = null;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                    }
                }
            });
            $scope.$watch('rt', recalculate);
            $scope.$watch('response.responseParts', recalculate, true);

            $scope.choose = function(part, option) {
                part.data.index = part.schema.options.indexOf(option);
                part.data.note = option.name;
                var nParts = $scope.rt.parts.length;
                var iPart = $scope.rt.parts.indexOf(part.schema);
                $scope.state.active = Math.min(iPart + 1, nParts - 1);
            };
            $scope.available = function(option) {
                if (!$scope.state.variables)
                    return false;
                return option.available($scope.state.variables);
            };

            $scope.checkRole = authz(current, $scope.survey);

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.which)) - 1;
                        i = Math.max(0, i);
                        i = Math.min($scope.rt.parts.length, i);
                        var part = $scope.rt.parts[$scope.state.active];
                        var option = part.options[i];
                        $scope.choose(part, option);
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
                            $scope.responseType.parts.length - 1,
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
                    description: "Stop editing comment",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        $scope.$broadcast('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
        }
    }
})


.controller('ResponseTypeEditorCtrl', function($scope, Numbers, dimmer) {
    $scope.dim = dimmer.toggler($scope);
    $scope.rtEdit = {};
    $scope.editRt = function(model, index) {
        var rt = angular.copy(model.responseTypes[index]);
        $scope.rtEdit = {
            model: model,
            rt: rt,
            i: index
        };
    };
    $scope.$watch('rtEdit.rt', function(rt) {
        $scope.dim(rt != null);
    });
    $scope.saveRt = function() {
        var rts = $scope.rtEdit.model.responseTypes;
        var rt = angular.copy($scope.rtEdit.rt);
        rt.parts.forEach(function (part) {
            // Clean up unused fields
            if (part.type != 'multiple_choice')
                delete part.options;
            if (part.type != 'numerical') {
                delete part.lower;
                delete part.upper;
            }
        });
        rts[$scope.rtEdit.i] = angular.copy(rt);
        $scope.rtEdit = {};
    };
    $scope.cancelRt = function() {
        $scope.rtEdit = {};
    };
    $scope.addRt = function(model) {
        var i = model.responseTypes.length + 1;
        model.responseTypes.push({
            id: 'response_' + i,
            name: 'Response Type ' + i,
            parts: []
        })
    };
    $scope.addPart = function(rt) {
        var ids = {};
        for (var i = 0; i < rt.parts.length; i++) {
            ids[rt.parts[i].id] = true;
        }
        var id;
        for (var i = 0; i <= rt.parts.length; i++) {
            id = Numbers.idOf(i);
            if (!ids[id])
                break;
        }
        var part = {
            id: id,
            name: 'Response part ' + id.toUpperCase(),
        };
        $scope.setType(part, 'multiple_choice');
        rt.parts.push(part);
        $scope.updateFormula(rt);
    };
    $scope.setType = function(part, type) {
        part.type = type;
        if (type == 'multiple_choice' && !part.options) {
            part.options = [
                {score: 0, name: 'No', 'if': null},
                {score: 1, name: 'Yes', 'if': null}
            ];
        }
    };
    $scope.addOption = function(part) {
        part.options.push({
            score: 0,
            name: 'Option ' + (part.options.length + 1)
        })
    };
    $scope.updateFormula = function(rt) {
        if (rt.parts.length <= 1) {
            rt.formula = null;
            return;
        }
        var formula = "";
        for (var i = 0; i < rt.parts.length; i++) {
            var part = rt.parts[i];
            if (i > 0)
                formula += " + ";
            if (part.id)
                formula += part.id;
            else
                formula += "?";
        }
        rt.formula = formula;
    };
    $scope.remove = function(rt, list, item) {
        var i = list.indexOf(item);
        if (i < 0)
            return;
        list.splice(i, 1);
        if (item.options)
            $scope.updateFormula(rt);
    };

    $scope.partTypes = [
        {name: 'multiple_choice', desc: 'Multiple choice'},
        {name: 'numerical', desc: 'Numerical'},
    ];
    $scope.partTypeMap = $scope.partTypes.reduce(function(ts, t){
        ts[t.name] = t.desc;
        return ts;
    }, {});
})


;
