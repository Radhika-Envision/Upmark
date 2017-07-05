'use strict'

angular.module('vpac.widgets.editor', [
    'upmark.notifications', 'upmark.user', 'vpac.utils.logging'])


/**
 * Manages state for a modal editing session.
 */
.factory('Editor', [
        '$parse', 'log', 'Notifications', '$q', 'checkLogin',
         function($parse, log, Notifications, $q, checkLogin) {

    function Editor(targetPath, scope, params, resource) {
        this.model = null;
        this.scope = scope;
        this.params = params;
        this.resource = resource;
        this.getter = $parse(targetPath);
        this.saving = false;
    };

    Editor.prototype.edit = function() {
        log.debug("Creating edit object");
        this.model = angular.copy(this.getter(this.scope));
    };

    Editor.prototype.cancel = function() {
        this.model = null;
        Notifications.remove('edit');
    };

    Editor.prototype.save = function() {
        this.scope.$broadcast('show-errors-check-validity');

        var that = this;
        var success = function(model, getResponseHeaders) {
            try {
                log.debug("Success");
                that.getter.assign(that.scope, model);
                that.model = null;
                that.scope.$emit('EditSaved', model);
                var message = "Saved";
                if (getResponseHeaders('Operation-Details'))
                    message += ": " + getResponseHeaders('Operation-Details');
                Notifications.set('edit', 'success', message, 5000);
            } finally {
                that.saving = false;
                that = null;
            }
            return model;
        };
        var failure = function(details) {
            var normalError = function() {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
            };
            var loginError = function() {
                Notifications.set('edit', 'error',
                    "Could not save: your session has expired.");
            };
            try {
                that.scope.$emit('EditError');
                if (details.status == 403) {
                    checkLogin().then(normalError, loginError);
                } else {
                    normalError();
                }
            } finally {
                that.saving = false;
                that = null;
            }
            return $q.reject(details);
        };

        var p;
        if (angular.isArray(this.model)) {
            log.info("Reordering list");
            p = this.resource.reorder(this.params, this.model, success, failure);
        } else if (!this.model.id) {
            log.info("Saving as new entry");
            p = this.model.$create(this.params, success, failure);
        } else {
            log.info("Saving over old entry");
            p = this.model.$save(this.params, success, failure);
        }
        this.saving = true;
        Notifications.set('edit', 'info', "Saving");
        return p;
    };

    Editor.prototype.del = function() {
        var that = this;
        var success = function(model, getResponseHeaders) {
            try {
                log.debug("Success");
                that.model = null;
                that.scope.$emit('EditDeleted', model);
                var message = "Deleted";
                if (getResponseHeaders('Operation-Details'))
                    message += ": " + getResponseHeaders('Operation-Details');
                Notifications.set('edit', 'success', message, 5000);
            } finally {
                that.saving = false;
                that = null;
            }
            return model;
        };
        var failure = function(details) {
            var normalError = function() {
                Notifications.set('edit', 'error',
                    "Could not delete object: " + details.statusText);
            };
            var loginError = function() {
                Notifications.set('edit', 'error',
                    "Could not delete object: your session has expired.");
            };
            try {
                that.scope.$emit('EditError');
                if (details.status == 403) {
                    checkLogin().then(normalError, loginError);
                } else {
                    normalError();
                }
            } finally {
                that.saving = false;
                that = null;
            }
            return $q.reject(details);
        };

        log.info("Deleting");
        var model = this.getter(this.scope);
        var p = model.$delete(this.params, success, failure);

        this.saving = true;
        Notifications.set('edit', 'info', "Deleting");
        return p;
    };

    Editor.prototype.undelete = function() {
        var that = this;
        var success = function(model, getResponseHeaders) {
            try {
                log.debug("Success");
                that.model = null;
                that.scope.$emit('EditSaved', model);
                var message = "Restored";
                if (getResponseHeaders('Operation-Details'))
                    message += ": " + getResponseHeaders('Operation-Details');
                Notifications.set('edit', 'success', message, 5000);
            } finally {
                that.saving = false;
                that = null;
            }
            return model;
        };
        var failure = function(details) {
            var normalError = function() {
                Notifications.set('edit', 'error',
                    "Could not restore object: " + details.statusText);
            };
            var loginError = function() {
                Notifications.set('edit', 'error',
                    "Could not restore object: your session has expired.");
            };
            try {
                that.scope.$emit('EditError');
                if (details.status == 403) {
                    checkLogin().then(normalError, loginError);
                } else {
                    normalError();
                }
            } finally {
                that.saving = false;
                that = null;
            }
            return $q.reject(details);
        };

        log.info("Deleting");
        var model = this.getter(this.scope);
        var p = model.$save(this.params, success, failure);

        this.saving = true;
        Notifications.set('edit', 'info', "Restoring");
        return p;
    };

    Editor.prototype.destroy = function() {
        this.model = null;
        this.scope = null;
        this.getter = null;
    };

    return function(targetPath, scope, params, resource) {
        log.debug('Creating editor');
        var editor = new Editor(targetPath, scope, params, resource);
        scope.$on('$destroy', function() {
            editor.destroy();
            editor = null;
        });
        return editor;
    };
}])