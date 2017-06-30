'use strict'

angular.module('vpac.utils.observer', [
    'vpac.utils.arrays'])


/**
 * Factory for convenience methods for the observer pattern.
 *
 * Usage:
 *     # Create the helper:
 *     $on = Observable();
 *     # Register a listener:
 *     $on('fooEvent', function(data) {
 *         console.log(data);
 *     });
 *     # Fire an event:
 *     $on.fire('fooEvent', 'bar');
 *     # Prints 'bar' to the console.
 */
.factory('Observable', [function() {
    return function() {
        var Observable = function(name, listener) {
            var listeners = Observable.listeners[name];
            if (!listeners) {
                listeners = [];
                Observable.listeners[name] = listeners;
            }
            listeners.push(listener);
            return function() {
                var index = listeners.indexOf(listener);
                if (index >= 0)
                    listeners.splice(index, 1);
            }
        };

        Observable.listeners = {};

        Observable.fire = function(name, data) {
            var listeners = Observable.listeners[name];
            if (!listeners)
                return;
            for (var i = 0; i < listeners.length; i++)
                listeners[i].call(null, data);
        };

        return Observable;
    };
}])


/*
 * Maintains a selection of objects, with one object as the "active" (focused)
 * member.
 */
.factory('WorkingSet', ['Arrays', 'Observable', function(Arrays, Observable) {
    function WorkingSet(primaryKey) {
        this.key = primaryKey;
        this.members = [];
        this.active = null;
        this.lastActive = null;
        this.$on = Observable();
    };
    WorkingSet.prototype.index = function(memberOrId) {
        var criterion = {};
        criterion[this.key] = memberOrId[this.key] || memberOrId;
        return Arrays.indexOf(this.members, criterion, this.key);
    };
    WorkingSet.prototype.get = function(memberOrId) {
        var index = this.index(memberOrId);
        if (index < 0)
            return null;
        return this.members[index];
    };
    WorkingSet.prototype.add = function(member) {
        var index = this.index(member);
        if (index >= 0)
            return;
        this.members.push(member);
        this.$on.fire('add', member);
    };
    WorkingSet.prototype.remove = function(member) {
        var index = this.index(member);
        if (index < 0)
            return;

        this.members.splice(index, 1);

        if (this.members.length > 0) {
            if (index == this.members.length)
                index--;
            this.activate(this.members[index]);
        } else {
            this.lastActive = null;
            this.activate(null);
        }
        this.$on.fire('remove', member);
    };
    WorkingSet.prototype.activate = function(member) {
        if (member != null) {
            this.add(member);
            this.lastActive = member;
        }
        this.active = member;
        this.$on.fire('activate', member);
    };

    return function(key) {
        return new WorkingSet(key);
    };
}])


;
