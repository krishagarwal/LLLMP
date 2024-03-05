from __future__ import annotations
from abc import abstractmethod, ABC
from typing import Any
import random
from typing import TypeVar, cast
from inspect import isabstract
import re
import os

DIR = os.path.dirname(__file__)

class Predicate:
	def __init__(self, name: str, parameter_list: list[str]) -> None:
		self.name = name
		self.parameter_list = parameter_list
	
	def __str__(self) -> str:
		return "({} {})".format(self.name, " ".join(self.parameter_list))

class Action:
	def __init__(self, name: str, parameter_list: list[str], preconditions: list[str], effects: list[str]) -> None:
		self.name = name
		self.parameter_list = parameter_list
		self.preconditions = preconditions
		self.effects = effects
	
	def __str__(self) -> str:
		return f"\t(:action {self.name}\n" \
					+ "\t\t:parameters ({})\n".format(" ".join(self.parameter_list)) \
					+ "\t\t:precondition (and\n" \
						+ "\t\t\t({})\n".format(")\n\t\t\t(".join(self.preconditions)) \
					+ "\t\t)\n" \
					+ "\t\t:effect (and\n" \
					+ "\t\t\t({})\n".format(")\n\t\t\t(".join(self.effects)) \
					+ "\t\t)\n" \
					+ "\t)\n"
	
class Goal:
	def __init__(self, description: str, predicate_list: list[str]) -> None:
		self.description = description
		self.predicate_list = predicate_list
	
	def __str__(self) -> str:
		return f"\t(:goal\n" \
					+ "\t\t(and\n" \
						+ "\t\t\t({})\n".format(")\n\t\t\t(".join(self.predicate_list)) \
					+ "\t\t)\n" \
				+ "\t)\n"

class EntityID:
	def __init__(self, name: str, concept: str):
		self.name = name
		self.concept = concept
	
	def __str__(self) -> str:
		return f'instance: ["{self.name}", "{self.concept}"]'

class Attribute:
	def __init__(self, name: str, value: EntityID | int | str | bool | float) -> None:
		self.name = name
		self.value = value
	
	def to_yaml(self, num_indent: int) -> str:
		indent = "  " * num_indent
		if isinstance(self.value, str):
			str_value = f'"{self.value}"'
		elif isinstance(self.value, EntityID):
			str_value = f"\n{indent}    {self.value}"
		else:
			str_value = str(self.value).lower()
		return f"{indent}- name: {self.name}\n" \
			   f"{indent}  value: {str_value}"

class Instance:
	def __init__(self, entity_id: EntityID, attributes: list[Attribute]):
		self.entity_id = entity_id
		self.attributes = attributes

	def to_yaml(self, num_indent: int) -> str:
		indent = "  " * num_indent
		yaml = f"{indent}- {self.entity_id}\n"
		if len(self.attributes) > 0:
			yaml += f"{indent}  attributes:\n"
			for attribute in self.attributes:
				yaml += attribute.to_yaml(num_indent + 1) + "\n"
		return yaml

class RoomItem(ABC):
	def initialize_entity_id(self):
		self.entity_id = EntityID(self.token_name, self.get_type_name())

	def __init__(self, name: str, token_name: str) -> None:
		self.name = name
		self.token_name = token_name
		self.initialize_entity_id()

	@abstractmethod
	def perform_action(self, person: Person) -> str | None:
		pass

	@staticmethod
	@abstractmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		pass

	@staticmethod
	@abstractmethod
	def get_pddl_domain_actions() -> list[Action]:
		pass

	@classmethod
	def get_type_name(cls) -> str:
		return cls.__name__.lower()

	@classmethod
	def get_required_types(cls) -> list[str]:
		return [cls.get_type_name() + " - object"]
	
	@abstractmethod
	def get_init_conditions(self) -> list[str]:
		pass

	def get_pddl_objects(self) -> list[str]:
		return [self.token_name + " - " + self.get_type_name()]
	
	@staticmethod
	def get_static_entities() -> list[Instance]:
		return []
	
	@abstractmethod
	def get_yaml_attributes(self) -> list[Attribute]:
		pass
	
	def get_yaml_instance(self) -> Instance:
		return Instance(self.entity_id, self.get_yaml_attributes())
	
	@abstractmethod
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		pass

class Queryable:
	@abstractmethod
	def generate_query_answer(self) -> tuple[str, str]:
		pass

class StationaryItem(RoomItem):
	def __init__(self, name: str, parent: Room) -> None:
		suffix = re.sub(r"[^a-zA-Z0-9]+", "_", name).lower()
		token_name = parent.token_name + "_" + suffix
		super().__init__(name, token_name)
		self.parent = parent
	
	@staticmethod
	@abstractmethod
	def generate_instance(parent: Room) -> tuple[StationaryItem, list[AccompanyingItem]]:
		pass

	@abstractmethod
	def get_description(self) -> str:
		pass

	def get_full_name_with_room(self) -> str:
		return f"{self.name} in {self.parent.name}"
	
	def get_init_conditions(self) -> list[str]:
		return [f"{Room.get_in_room_relation()} {self.parent.token_name} {self.token_name}"]
	
	def get_yaml_attributes(self) -> list[Attribute]:
		return []

class MovableItem(RoomItem, Queryable):
	def __init__(self, name: str, token_name: str, shortened_name: str, use_default_article: bool = True) -> None:
		super().__init__(name, token_name)
		self.set_shortened_name(shortened_name, use_default_article)
		self.container: Container | Person
		self.relative_location: str | None = None
		self.extra_location_info: dict[Any, Any] = {}
	
	def generate_query_answer(self) -> tuple[str, str]:
		query = f"Where is {self.shortened_name}?"
		if isinstance(self.container, Person):
			answer = f"You are holding {self.shortened_name}."
		else:
			answer = f"{self.shortened_name.capitalize()} is {self.relative_location} the {self.container.get_full_name_with_room()}."
		return query, answer
	
	def perform_action(self, person: Person) -> str | None:
		return None

	@staticmethod
	@abstractmethod
	def generate_instance() -> MovableItem | None:
		pass

	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return []
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return []
	
	def get_init_conditions(self) -> list[str]:
		if isinstance(self.container, Person):
			return [Person.get_in_hand_predicate(self.container.token_name, self.token_name)]
		return self.container.get_contains_predicates(self.container.token_name, self.token_name, **self.extra_location_info)
	
	def get_yaml_attributes(self) -> list[Attribute]:
		attributes = [Attribute(Person.get_in_hand_relation() if isinstance(self.container, Person) else self.container.get_contains_relation(), self.container.entity_id)]
		if "extra_attributes" in self.extra_location_info.keys():
			extras = self.extra_location_info.get("extra_attributes")
			assert isinstance(extras, list)
			attributes += extras
		return attributes
	
	def set_shortened_name(self, shortened_name: str, use_default_article: bool) -> None:
		self.shortened_name = "{}{}".format("the " if use_default_article else "", shortened_name)
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if self in person.items:
			return None
		self.container.items.remove(self)
		person.items.append(self)
		self.container = person
		self.relative_location = None
		self.extra_location_info = {}
		return Goal(
			f"Hand me {self.shortened_name}.",
			[person.get_in_hand_predicate(person.token_name, self.token_name)]
		)

class AccompanyingItem(MovableItem):
	def __init__(self, name: str, token_name: str, shortened_name: str, use_default_article: bool = True) -> None:
		super().__init__(name, token_name, shortened_name, use_default_article)
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		return None

class Container(StationaryItem):
	ITEM_PARAM = "?a"
	CONTAINER_PARAM = "?b"
	PERSON_PARAM = "?c"
	EXTRA_INFO: dict[str, Any] = {}

	def __init__(self, name: str, parent: Room) -> None:
		super().__init__(name, parent)
		self.items: list[MovableItem]

	@staticmethod
	@abstractmethod
	def can_hold(item_type: type[MovableItem]) -> bool:
		pass

	@classmethod
	def get_holdable_types(cls) -> list[type[MovableItem]]:
		return [movable_type for movable_type in movable_types if cls.can_hold(movable_type)]
	
	def populate(self, items: list[MovableItem], max_allowed: int) -> None:
		self.items = []
		holdables = [item for item in items if self.can_hold(type(item))]
		random.shuffle(holdables)
		while len(holdables) > 0 and len(self.items) < max_allowed:
			item = holdables.pop()
			items.remove(item)
			self.items.append(item)
		for item in self.items:
			item.container = self
			item.relative_location, item.extra_location_info = self.generate_relative_location()
		random.shuffle(self.items)
	
	def get_description(self) -> str:
		if len(self.items) == 0:
			return f"The {self.name} is empty. "
		return f"The {self.name} has {self.get_item_list_description(self.items)}. "
	
	@staticmethod
	def get_item_list_description(item_list: list[MovableItem]) -> str:
		description = ""
		for i, item in enumerate(item_list):
			description += "a{} {}".format("n" if item.name[0] in "aeiou" else "", item.name)
			if len(item_list) == 2 and i == 0:
				description += " and "
			else:
				if i < len(item_list) - 1 and (i != len(item_list) - 2 or len(item_list) > 2):
					description += ", "
				if i == len(item_list) - 2:
					description += "and "
		return description
	
	@abstractmethod
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		pass

	def perform_action(self, person: Person) -> str | None:
		items = person.items.copy()
		random.shuffle(items)
		for item in items:
			if not self.can_hold(type(item)):
				continue
			person.items.remove(item)
			self.items.append(item)
			item.container = self
			item.relative_location, item.extra_location_info = self.generate_relative_location()
			return f"I placed {item.shortened_name} {item.relative_location} the {self.get_full_name_with_room()}."
		return None
		
	@classmethod
	def get_contains_relation(cls) -> str:
		return f"placed_at_{cls.get_type_name()}"

	@classmethod
	def get_place_action_name(cls) -> str:
		return f"place_at_{cls.get_type_name()}"

	@classmethod
	def get_remove_action_name(cls) -> str:
		return f"remove_from_{cls.get_type_name()}"
	
	@classmethod
	def get_contains_predicates(cls, container_param: str, item_param: str, **kwargs) -> list[str]:
		return [f"{cls.get_contains_relation()} {item_param} {container_param}"]
	
	@classmethod
	def get_holdable_param(cls, param_token: str) -> str:
		holdable_types = [holdable_type.get_type_name() for holdable_type in cls.get_holdable_types()]
		return "{} - (either {})".format(param_token, " ".join(holdable_types))

	@classmethod
	def get_default_param_list(cls) -> list[str]:
		return [cls.get_holdable_param(cls.ITEM_PARAM), f"{cls.CONTAINER_PARAM} - {cls.get_type_name()}"]
	
	@classmethod
	def get_pddl_domain_predicates(cls) -> list[Predicate]:
		return [Predicate(cls.get_contains_relation(), [cls.get_holdable_param(cls.ITEM_PARAM), f"{cls.CONTAINER_PARAM} - {cls.get_type_name()}"])]
	
	@classmethod
	def get_place_action(cls) -> Action:
		param_list = cls.get_default_param_list()
		holding_predicate = AgentConstants.get_holding_predicate(cls.ITEM_PARAM)
		contains_predicates = cls.get_contains_predicates(cls.CONTAINER_PARAM, cls.ITEM_PARAM, **cls.EXTRA_INFO)

		place_preconditions = [holding_predicate]
		place_effects = [f"not ({holding_predicate})"] + contains_predicates

		return Action(cls.get_place_action_name(), param_list, place_preconditions, place_effects)
	
	@classmethod
	def get_remove_action(cls) -> Action:
		param_list = cls.get_default_param_list()
		holding_predicate = AgentConstants.get_holding_predicate(cls.ITEM_PARAM)
		contains_predicates = cls.get_contains_predicates(cls.CONTAINER_PARAM, cls.ITEM_PARAM, **cls.EXTRA_INFO)

		remove_preconditions = contains_predicates
		remove_effects = [f"not ({pred})" for pred in contains_predicates] + [holding_predicate]

		return Action(cls.get_remove_action_name(), param_list, remove_preconditions, remove_effects)
	
	@classmethod
	def get_pddl_domain_actions(cls) -> list[Action]:
		return [cls.get_place_action(), cls.get_remove_action()]
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		random.shuffle(all_items)
		for item in all_items:
			if not self.can_hold(type(item)):
				continue
			item.container.items.remove(item)
			self.items.append(item)
			item.container = self
			item.relative_location, item.extra_location_info = self.generate_relative_location()
			return Goal(
				f"Place {item.shortened_name} {item.relative_location} the {self.get_full_name_with_room()}.",
				self.get_contains_predicates(self.token_name, item.token_name, **item.extra_location_info)
			)
		return None

class InteractableItem(RoomItem, Queryable):
	@abstractmethod
	def get_special_init_conditions(self) -> list[str]:
		pass

	@abstractmethod
	def get_special_yaml_attributes(self) -> list[Attribute]:
		pass

class StationaryInteractable(StationaryItem, InteractableItem):
	def get_init_conditions(self) -> list[str]:
		return StationaryItem.get_init_conditions(self) + self.get_special_init_conditions()
	
	def get_yaml_attributes(self) -> list[Attribute]:
		return StationaryItem.get_yaml_attributes(self) + self.get_special_yaml_attributes()

class MovableInteractable(MovableItem, InteractableItem):
	@abstractmethod
	def generate_interactable_qa(self) -> tuple[str, str]:
		pass

	def generate_query_answer(self) -> tuple[str, str]:
		return self.generate_interactable_qa() if random.choice([True, False]) else MovableItem.generate_query_answer(self)
	
	@abstractmethod
	def interact(self, person: Person) -> str | None:
		pass

	@staticmethod
	@abstractmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		pass

	@staticmethod
	@abstractmethod
	def get_pddl_domain_actions() -> list[Action]:
		pass

	def perform_action(self, person: Person) -> str | None:
		while True:
			action = self.interact(person) if random.choice([True, False]) else MovableItem.perform_action(self, person)
			if action is not None:
				return action

	def get_init_conditions(self) -> list[str]:
		return MovableItem.get_init_conditions(self) + self.get_special_init_conditions()
	
	def get_yaml_attributes(self) -> list[Attribute]:
		return MovableItem.get_yaml_attributes(self) + self.get_special_yaml_attributes()

class InteractableContainer(Container, StationaryInteractable):
	@abstractmethod
	def interact(self, person: Person) -> str | None:
		pass

	def perform_action(self, person: Person) -> str | None:
		while True:
			action = self.interact(person) if random.choice([True, False]) else Container.perform_action(self, person)
			if action is not None:
				return action
	
	@abstractmethod
	def generate_interactable_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		pass

	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if random.choice([True, False]):
			goal = self.generate_interactable_goal(person, all_items)
			if goal is None:
				goal = Container.generate_goal(self, person, all_items)
			return goal
		goal = Container.generate_goal(self, person, all_items)
		if goal is None:
			goal = self.generate_interactable_goal(person, all_items)
		return goal
	
	def get_init_conditions(self) -> list[str]:
		return Container.get_init_conditions(self) + self.get_special_init_conditions()
	
	def get_yaml_attributes(self) -> list[Attribute]:
		return Container.get_yaml_attributes(self) + self.get_special_yaml_attributes()
	
	@abstractmethod
	def get_interactable_description(self) -> str:
		pass

	def get_container_description(self) -> str:
		return Container.get_description(self)
	
	def get_description(self) -> str:
		return self.get_container_description() + self.get_interactable_description()

	@staticmethod
	@abstractmethod
	def get_special_domain_predicates() -> list[Predicate]:
		pass

	@classmethod
	def get_pddl_domain_predicates(cls) -> list[Predicate]:
		return super().get_pddl_domain_predicates() + cls.get_special_domain_predicates()
	
	@staticmethod
	@abstractmethod
	def get_special_domain_actions() -> list[Action]:
		pass

	@classmethod
	def get_pddl_domain_actions(cls) -> list[Action]:
		return super().get_pddl_domain_actions() + cls.get_special_domain_actions()

class Table(Container):
	@staticmethod
	def can_hold(item_type: type[MovableItem]) -> bool:
		return True
	
	@staticmethod
	def generate_instance(parent: Room) -> tuple[Table, list[AccompanyingItem]]:
		return Table("table", parent), []
	
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		return "on", {}
	
class Shelf(Container):
	MIN_LEVELS = 3
	MAX_LEVELS = 10
	LEVEL_PARAM = "?c"
	PERSON_PARAM = "?d"
	LEVEL_TYPE = "shelf_level"
	EXTRA_INFO: dict[str, Any] = {"level_token" : LEVEL_PARAM}

	@staticmethod
	def get_level_name(level: int) -> str:
		return "shelf_level_" + str(level)
	
	LEVEL_OBJECTS: list[Instance] = []
	for i in range(MAX_LEVELS):
		LEVEL_OBJECTS.append(Instance(EntityID(get_level_name.__func__(i + 1), LEVEL_TYPE), []))

	def __init__(self, parent: Room, levels: int) -> None:
		super().__init__("shelf", parent)
		self.levels = levels
	
	@staticmethod
	def can_hold(item_type: type[MovableItem]) -> bool:
		return True
	
	@staticmethod
	def generate_instance(parent: Room) -> tuple[Shelf, list[AccompanyingItem]]:
		return Shelf(parent, random.randint(Shelf.MIN_LEVELS, Shelf.MAX_LEVELS)), []
	
	def get_description(self) -> str:
		items_by_level: dict[int, list[MovableItem]] = {level : [] for level in range(1, self.levels + 1)}
		for item in self.items:
			items_by_level[item.extra_location_info["level_num"]].append(item)
		description = f"The shelf has {self.levels} levels. "
		for level, item_list in items_by_level.items():
			if len(item_list) == 0:
				continue
			description += f"The {Shelf.integer_to_ordinal(level)} level of the shelf has {Shelf.get_item_list_description(item_list)}. "
		return description
	
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		level = random.randrange(self.levels) + 1
		return f"on the {Shelf.integer_to_ordinal(level)} level of", \
				{
					"level_num" : level,
					"level_token": self.get_level_name(level),
					"extra_attributes": [Attribute("on_shelf_level", Shelf.LEVEL_OBJECTS[level - 1].entity_id)]
				}

	@staticmethod
	def integer_to_ordinal(number):
		if number % 100 in [11, 12, 13]:
			return str(number) + "th"
		elif number % 10 == 1:
			return str(number) + "st"
		elif number % 10 == 2:
			return str(number) + "nd"
		elif number % 10 == 3:
			return str(number) + "rd"
		else:
			return str(number) + "th"
		
	@classmethod
	def get_pddl_domain_predicates(cls) -> list[Predicate]:
		predicates = super().get_pddl_domain_predicates()
		predicates.append(Predicate("shelf_has_level", [f"?a - {cls.get_type_name()}", f"?b - {cls.LEVEL_TYPE}"]))
		predicates.append(Predicate("on_shelf_level", [cls.get_holdable_param("?a"), f"?b - {cls.LEVEL_TYPE}"]))
		return predicates
	
	@classmethod
	def get_place_action(cls) -> Action:
		place = super().get_place_action()
		place.preconditions.append(f"shelf_has_level {super().CONTAINER_PARAM} {cls.LEVEL_PARAM}")
		return place
	
	@classmethod
	def get_default_param_list(cls) -> list[str]:
		param_list = super().get_default_param_list()
		param_list.append(f"{cls.LEVEL_PARAM} - {cls.LEVEL_TYPE}")
		return param_list
	
	@classmethod
	def get_contains_predicates(cls, container_param: str, item_param: str, **kwargs) -> list[str]:
		return super().get_contains_predicates(container_param, item_param) + [f"on_shelf_level {item_param} {kwargs['level_token']}"]
	
	@classmethod
	def get_required_types(cls) -> list[str]:
		types = super().get_required_types()
		types.append(cls.LEVEL_TYPE)
		return types
	
	def get_init_conditions(self) -> list[str]:
		conditions = super().get_init_conditions()
		for i in range(self.levels):
			conditions.append(f"shelf_has_level {self.token_name} {self.get_level_name(i + 1)}")
		return conditions
	
	def get_yaml_attributes(self) -> list[Attribute]:
		attributes = Container.get_yaml_attributes(self)
		for i in range(self.levels):
			attributes.append(Attribute("shelf_has_level", Shelf.LEVEL_OBJECTS[i].entity_id))
		return attributes
	
	@staticmethod
	def get_static_entities() -> list[Instance]:
		return Shelf.LEVEL_OBJECTS

class Fridge(Container):
	def __init__(self, name: str, parent: Room, foods: list[Food]) -> None:
		super().__init__(name, parent)
		self.foods = foods

	@staticmethod
	def can_hold(item_type: type[MovableItem]) -> bool:
		return issubclass(item_type, Food)
	
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		return "inside", {}

	@staticmethod
	def generate_instance(parent: Room) -> tuple[Fridge, list[Food]]:
		foods: list[Food] = []
		food_item = Food.generate_instance()
		while food_item is not None and len(foods) < 5:
			foods.append(cast(Food, food_item))
			food_item = Food.generate_instance()
		return Fridge("fridge", parent, foods), foods
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if random.choice([True, False]):
			goal = super().generate_goal(person, all_items)
			if goal is not None:
				return goal
		predicates: list[str] = []
		for food in self.foods:
			if self != food.container:
				food.container.items.remove(food)
				self.items.append(food)
				food.container = self
				food.relative_location, food.extra_location_info = self.generate_relative_location()
			predicates += self.get_contains_predicates(self.token_name, food.token_name, **food.extra_location_info)
		return Goal(
			f"Please return all food items to the {self.name} in {self.parent.name}.",
			predicates
		)


class Sink(StationaryInteractable):
	FAUCET_ON_RELATION = "faucet_on"

	def __init__(self, name: str, parent: Room, faucet_on: bool) -> None:
		super().__init__(name, parent)
		self.faucet_on = faucet_on

	def generate_query_answer(self) -> tuple[str, str]:
		return f"Is the faucet of the {self.get_full_name_with_room()} on or off?", "The faucet is {}.".format("on" if self.faucet_on else "off")
	
	def perform_action(self, person: Person) -> str | None:
		self.faucet_on = not self.faucet_on
		return "I turned {} the faucet of the {}.".format("on" if self.faucet_on else "off", self.get_full_name_with_room())
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [Predicate(Sink.FAUCET_ON_RELATION, ["?a - " + Sink.get_type_name()])]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("turn_on_faucet", ["?a - " + Sink.get_type_name()], [f"not ({Sink.FAUCET_ON_RELATION} ?a)"], [f"{Sink.FAUCET_ON_RELATION} ?a"]),
			Action("turn_off_faucet", ["?a - " + Sink.get_type_name()], [f"{Sink.FAUCET_ON_RELATION} ?a"], [f"not ({Sink.FAUCET_ON_RELATION} ?a)"])
		]
	
	def get_special_init_conditions(self) -> list[str]:
		if self.faucet_on:
			return [f"{Sink.FAUCET_ON_RELATION} {self.token_name}"]
		return []
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute(Sink.FAUCET_ON_RELATION, self.faucet_on)]
	
	@staticmethod
	def generate_instance(parent: Room) -> tuple[Sink, list[AccompanyingItem]]:
		return Sink("sink", parent, random.choice([True, False])), []
	
	def get_description(self) -> str:
		return "The sink has a faucet that can be turned on and off. It is currently {}. ".format("on" if self.faucet_on else "off")
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if self.faucet_on:
			self.faucet_on = False
			return Goal(f"Turn off the faucet of the {self.get_full_name_with_room()}.", [f"{Sink.FAUCET_ON_RELATION} {self.token_name}"])

class KitchenSink(InteractableContainer):
	def __init__(self, name: str, parent: Room, faucet_on: bool, dishes: list[Kitchenware | LiquidContainer]) -> None:
		super().__init__(name, parent)
		self.faucet_on = faucet_on
		self.dishes = dishes

	@staticmethod
	def can_hold(item_type: type[MovableItem]) -> bool:
		return issubclass(item_type, Kitchenware) or issubclass(item_type, LiquidContainer)
	
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		return "in", {}

	def interact(self, person: Person) -> str | None:
		self.faucet_on = not self.faucet_on
		return "I turned {} the faucet of the {}.".format("on" if self.faucet_on else "off", self.get_full_name_with_room())
	
	def generate_query_answer(self) -> tuple[str, str]:
		return f"Is the faucet of the {self.get_full_name_with_room()} on or off?", "The faucet is {}.".format("on" if self.faucet_on else "off")
	
	def get_special_init_conditions(self) -> list[str]:
		if self.faucet_on:
			return [f"{Sink.FAUCET_ON_RELATION} {self.token_name}"]
		return []
	
	def get_interactable_description(self) -> str:
		return "The sink has a faucet that can be turned on and off. It is currently {}. ".format("on" if self.faucet_on else "off")
	
	@staticmethod
	def get_special_domain_predicates() -> list[Predicate]:
		return []
	
	@staticmethod
	def get_special_domain_actions() -> list[Action]:
		return []
	
	@classmethod
	def get_required_types(cls) -> list[str]:
		return [f"{cls.get_type_name()} - {Sink.get_type_name()}"]
	
	@staticmethod
	def generate_instance(parent: Room) -> tuple[KitchenSink, list[Kitchenware | LiquidContainer]]:
		dishes: list[Kitchenware | LiquidContainer] = []
		dish = Kitchenware.generate_instance()
		while dish is not None and len(dishes) < 5:
			dishes.append(cast(Kitchenware, dish))
			dish = Kitchenware.generate_instance()
		glass = LiquidContainer.generate_instance()
		if glass is not None:
			dishes.append(glass)
		return KitchenSink("sink", parent, random.choice([True, False]), dishes), dishes
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute(Sink.FAUCET_ON_RELATION, self.faucet_on)]
	
	def generate_interactable_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if random.choice([True, False]):
			goal = Sink.generate_goal(self, person, all_items) # type: ignore
			if goal is not None:
				return goal 
		predicates: list[str] = []
		for dish in self.dishes:
			if self != dish.container:
				dish.container.items.remove(dish)
				self.items.append(dish)
				dish.container = self
				dish.relative_location, dish.extra_location_info = self.generate_relative_location()
			predicates += self.get_contains_predicates(self.token_name, dish.token_name, **dish.extra_location_info)
		return Goal(
			f"Please return all dishes to the {self.name} in {self.parent.name}.",
			predicates
		)

class Book(MovableItem):
	with open(os.path.join(DIR, "book_titles.txt")) as f:	
		available_titles = f.read().splitlines()

	def __init__(self, title: str) -> None:
		prefix = re.sub(r"[^a-zA-Z0-9]+", "_", title).lower()
		super().__init__(f'book called "{title}"', prefix + "_book", f'"{title}" book')

	@staticmethod
	def generate_instance() -> Book | None:
		if len(Book.available_titles) == 0:
			return None
		idx = random.randrange(len(Book.available_titles))
		return Book(Book.available_titles.pop(idx))

class Pen(MovableItem):
	with open(os.path.join(DIR, "colors.txt")) as f:	
		available_colors = f.read().lower().splitlines()

	def __init__(self, color: str) -> None:
		super().__init__(f"{color} pen", color + "_pen", f"{color} pen")
	
	@staticmethod
	def generate_instance() -> Pen | None:
		if len(Pen.available_colors) == 0:
			return None
		idx = random.randrange(len(Pen.available_colors))
		return Pen(Pen.available_colors.pop(idx))

class Singleton(MovableItem):
	def __init__(self, name: str) -> None:
		token_name = re.sub(r"[^a-zA-Z0-9]+", "_", name).lower()
		super().__init__(name, token_name, name)
	
	@staticmethod
	@abstractmethod
	def get_available_names() -> list[str]:
		pass

	@classmethod
	def generate_instance(cls) -> Singleton | None:
		names = cls.get_available_names()
		if len(names) == 0:
			return None
		return cls(names.pop(random.randrange(len(names))))

class Food(Singleton, AccompanyingItem):
	with open(os.path.join(DIR, "foods.txt")) as f:
		available_foods = f.read().lower().splitlines()
	
	@staticmethod
	def get_available_names() -> list[str]:
		return Food.available_foods

class Kitchenware(Singleton, AccompanyingItem):
	available_kitchenware = ["plate", "bowl", "fork", "spoon", "knife"]

	@staticmethod
	def get_available_names() -> list[str]:
		return Kitchenware.available_kitchenware

class Window(StationaryInteractable):
	def __init__(self, parent: Room, open: bool) -> None:
		super().__init__("window", parent)
		self.open = open
	
	def generate_query_answer(self) -> tuple[str, str]:
		return f"Are the blinds of the {self.get_full_name_with_room()} open or closed?", "The window blinds are {}.".format("open" if self.open else "closed")
	
	def perform_action(self, person: Person) -> str | None:
		self.open = not self.open
		return "I {} the blinds of the {}.".format("opened" if self.open else "closed", self.get_full_name_with_room())
	
	def get_description(self) -> str:
		return "The window has blinds that can open and close. They are currently {}. ".format("open" if self.open else "closed")

	@staticmethod
	def generate_instance(parent: Room) -> tuple[Window, list[AccompanyingItem]]:
		return Window(parent, random.choice([True, False])), []
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [Predicate("window_open", ["?a - window"])]

	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("open_window", ["?a - window"], ["not (window_open ?a)"], ["window_open ?a"]),
			Action("close_window", ["?a - window"], ["window_open ?a"], ["not (window_open ?a)"])
		]
	
	def get_special_init_conditions(self) -> list[str]:
		if self.open:
			return ["window_open " + self.token_name]
		return []
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("window_open", self.open)]
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		self.open = not self.open
		pred = f"window_open {self.token_name}"
		return Goal("{} the blinds of the {}.".format("Open" if self.open else "Close", self.get_full_name_with_room()), [pred if self.open else f"not ({pred})"])

class Light(StationaryInteractable):
	def __init__(self, name: str, parent: Room, on: bool) -> None:
		super().__init__(name, parent)
		self.on = on
	
	def generate_query_answer(self) -> tuple[str, str]:
		return f"Is the {self.get_full_name_with_room()} on or off?", "The light is {}.".format("on" if self.on else "off")
	
	def perform_action(self, person: Person) -> str | None:
		self.on = not self.on
		return "I turned {} the {}.".format("on" if self.on else "off", self.get_full_name_with_room())
	
	def get_description(self) -> str:
		return "The light turns on and off. It is currently {}. ".format("on" if self.on else "off")
	
	@staticmethod
	def generate_instance(parent: Room) -> tuple[Light, list[AccompanyingItem]]:
		return Light("overhead light", parent, random.choice([True, False])), []
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [Predicate("light_on", ["?a - " + Light.get_type_name()])]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("turn_on_light", ["?a - " + Light.get_type_name()], ["not (light_on ?a)"], ["light_on ?a"]),
			Action("turn_off_light", ["?a - " + Light.get_type_name()], ["light_on ?a"], ["not (light_on ?a)"])
		]
	
	def get_special_init_conditions(self) -> list[str]:
		if self.on:
			return ["light_on " + self.token_name]
		return []
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("light_on", self.on)]
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		self.on = not self.on
		pred = f"light_on {self.token_name}"
		return Goal("Turn {} the {}.".format("on" if self.on else "off", self.get_full_name_with_room()), [pred if self.on else f"not ({pred})"])

class Remote(AccompanyingItem):
	def __init__(self, name: str) -> None:
		token_name = re.sub(r"[^a-zA-Z0-9]+", "_", name).lower()
		super().__init__(name, token_name, name, True)

	@staticmethod
	def generate_instance() -> Remote | None:
		return Remote("remote")

class TV(StationaryInteractable):
	class Channel:
		TYPE_NAME = "channel"
		def __init__(self, name: str) -> None:
			self.name = name
			self.token_name = re.sub(r"[^a-zA-Z0-9]+", "_", name).lower()
			self.entity_id = EntityID(self.token_name, "channel")

	CHANNELS = [
		Channel("the Discovery Channel"),
		Channel("Cartoon Network"),
		Channel("NBC"),
		Channel("CNN"),
		Channel("Fox News"),
		Channel("ESPN")
	]
	CHANNEL_OBJECTS = [Instance(channel.entity_id, []) for channel in CHANNELS]

	def __init__(self, parent: Room, on: bool, curr_channel: Channel, remote: Remote) -> None:
		super().__init__("TV", parent)
		self.on = on
		self.curr_channel = curr_channel
		self.remote = remote
		remote.name = f"remote for {parent.name} TV"
		remote.set_shortened_name(remote.name, True)
		self.remote.token_name = self.token_name + "_remote"
		self.remote.initialize_entity_id()
	
	def generate_query_answer(self) -> tuple[str, str]:
		query = f"Is the TV in {self.parent.name} on or off? If it's on, what channel is it playing?"
		answer = "The TV is {}{}.".format("on" if self.on else "off", f" and is playing {self.curr_channel.name}" if self.on else "")
		return query, answer
	
	def perform_action(self, person: Person) -> str | None:
		if self.remote not in person.items:
			return None
		if self.on:
			# keep the TV on
			if random.choice([True, False]):
				self.curr_channel = random.choice(TV.CHANNELS)
				return f"I switched the channel of the TV in {self.parent.name} to {self.curr_channel.name}."
			# turn the TV off
			self.on = False
			return f"I turned off the TV in {self.parent.name}."
		self.on = True
		self.curr_channel = random.choice(TV.CHANNELS)
		return f"I turned on the TV in {self.parent.name} and set it to {self.curr_channel.name}."
	
	def get_description(self) -> str:
		if self.on:
			return f"The TV is currently on and is playing {self.curr_channel.name}. "
		return "The TV is currently off. "
	
	@staticmethod
	def generate_instance(parent: Room) -> tuple[TV, list[AccompanyingItem]]:
		remote = Remote.generate_instance()
		assert remote is not None
		return TV(parent, random.choice([True, False]), random.choice(TV.CHANNELS), remote), [remote]
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [Predicate("tv_on", ["?a - tv"]), Predicate("tv_playing_channel", ["?a - tv", "?b - channel"])]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("turn_tv_on", ["?a - tv", "?b - channel"], ["not (tv_on ?a)"], ["tv_on ?a", "tv_playing_channel ?a ?b"]),
			Action("turn_tv_off", ["?a - tv", "?b - channel"], ["tv_on ?a", "tv_playing_channel ?a ?b"], ["not (tv_on ?a)", "not (tv_playing_channel ?a ?b)"]),
			Action("switch_tv_channel", ["?a - tv", "?b - channel", "?c - channel"], ["tv_playing_channel ?a ?b"], ["tv_playing_channel ?a ?c", "not (tv_playing_channel ?a ?b)"])
		]
	
	@classmethod
	def get_required_types(cls) -> list[str]:
		types = super().get_required_types()
		types.append(cls.Channel.TYPE_NAME)
		return types
	
	def get_special_init_conditions(self) -> list[str]:
		if self.on:
			return ["tv_on " + self.token_name, f"tv_playing_channel {self.token_name} {self.curr_channel.token_name}"]
		return []
	
	@staticmethod
	def get_static_entities() -> list[Instance]:
		return TV.CHANNEL_OBJECTS
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		attributes = [Attribute("tv_on", self.on)]
		if self.on:
			attributes.append(Attribute("tv_playing_channel", self.curr_channel.entity_id))
		return attributes
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if self.remote in person.items:
			return None
		assert isinstance(self.remote.container, Container)
		self.remote.container.items.remove(self.remote)
		person.items.append(self.remote)
		self.remote.container = person
		self.remote.relative_location = None
		self.remote.extra_location_info = {}
		return Goal(
			f"I am trying to use the TV in {self.parent.name} but I need the remote. Please hand it to me.",
			[person.get_in_hand_predicate(person.token_name, self.remote.token_name)]
		)

class Phone(MovableInteractable):
	with open(os.path.join(DIR, "names.txt")) as f:	
		available_names = f.read().splitlines()

	def __init__(self, owner: str) -> None:
		super().__init__(f"phone that belongs to {owner}", owner.lower() + "_phone", f"{owner}'s phone", use_default_article=False)
		self.ringing = False
	
	def get_special_init_conditions(self) -> list[str]:
		if self.ringing:
			return ["phone_ringing " + self.token_name]
		return []
	
	def generate_interactable_qa(self) -> tuple[str, str]:
		return f"Is {self.shortened_name} ringing?", "Yes." if self.ringing else "No."
	
	def interact(self, person: Person) -> str | None:
		self.ringing = not self.ringing
		return "{} {} ringing.".format(self.shortened_name, "started" if self.ringing else "stopped")
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [Predicate("phone_ringing", ["?a - " + Phone.get_type_name()])]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [Action("answer_phone", ["?a - " + Phone.get_type_name()], ["phone_ringing ?a"], ["not (phone_ringing ?a)"])]

	@staticmethod
	def generate_instance() -> Phone | None:
		if len(Phone.available_names) == 0:
			return None
		return Phone(Phone.available_names.pop(random.randrange(len(Phone.available_names))))
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("phone_ringing", self.ringing)]
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if random.choice([True, False]):
			goal = super().generate_goal(person, all_items)
			if goal is not None:
				return goal
		if self.ringing:
			self.ringing = False
			return Goal(f"Answer {self.shortened_name}.", [f"not (phone_ringing {self.token_name})"])
		return None

class LiquidContainer(MovableInteractable, AccompanyingItem):
	generated = False

	LIQUIDS: list[Instance] = []
	for l in ["water", "juice", "coffee", "soda"]:
		LIQUIDS.append(Instance(EntityID(l, "liquid"), []))
	
	def __init__(self) -> None:
		super().__init__(f"glass", "glass", "glass")
		self.empty = random.choice([True, False])
		if self.empty:
			self.liquid = None
		else:
			self.liquid = random.choice(LiquidContainer.LIQUIDS)
	
	def get_special_init_conditions(self) -> list[str]:
		if self.empty:
			return ["glass_empty " + self.token_name]
		assert(isinstance(self.liquid, Instance))
		return [f"glass_has_liquid {self.token_name} {self.liquid.entity_id.name}"]
	
	def generate_interactable_qa(self) -> tuple[str, str]:
		liquid = ""
		if not self.empty:
			assert(isinstance(self.liquid, Instance))
			liquid = self.liquid.entity_id.name
		return f"Is {self.shortened_name} empty? If not, what does it contain?", "It is empty." if self.empty else f"It is not empty. It contains {liquid}."
	
	def interact(self, person: Person) -> str | None:
		if self.empty:
			self.empty = False
			self.liquid = random.choice(LiquidContainer.LIQUIDS)
			return f"I filled {self.shortened_name} with {self.liquid.entity_id.name}."
		self.empty = True
		self.liquid = None
		return f"I emptied {self.shortened_name}."
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [
			Predicate("glass_empty", ["?a - " + LiquidContainer.get_type_name()]),
			Predicate("glass_has_liquid", ["?a - " + LiquidContainer.get_type_name(), "?b - liquid"])
		  ]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("empty_glass", ["?a - " + LiquidContainer.get_type_name(), "?b - liquid"], ["glass_has_liquid ?a ?b"], ["glass_empty ?a", "not (glass_has_liquid ?a ?b)"]),
			Action("fill_with_liquid", ["?a - " + LiquidContainer.get_type_name(), "?b - liquid"], ["glass_empty ?a"], ["not (glass_empty ?a)", "glass_has_liquid ?a ?b"])
		]

	@staticmethod
	def generate_instance() -> LiquidContainer | None:
		if LiquidContainer.generated:
			return None
		LiquidContainer.generated = True
		return LiquidContainer()
		
	def get_special_yaml_attributes(self) -> list[Attribute]:
		attributes = [Attribute("glass_empty", self.empty)]
		if not self.empty:
			assert(isinstance(self.liquid, Instance))
			attributes.append(Attribute("glass_has_liquid", self.liquid.entity_id))
		return attributes
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		if not self.empty and random.choice([True, False]):
			self.empty = True
			self.liquid = None
			return Goal("Empty the glass.", ["glass_empty " + self.token_name])
		self.empty = False
		self.liquid = random.choice(LiquidContainer.LIQUIDS)
		
		self.container.items.remove(self)
		person.items.append(self)
		self.container = person
		self.relative_location = None
		self.extra_location_info = {}
		return Goal(
			f"Hand me a glass of {self.liquid.entity_id.name}.",
			[person.get_in_hand_predicate(person.token_name, self.token_name), f"glass_has_liquid {self.token_name} {self.liquid.entity_id.name}"]
		)
	
	@staticmethod
	def get_static_entities() -> list[Instance]:
		return LiquidContainer.LIQUIDS
	
	@classmethod
	def get_required_types(cls) -> list[str]:
		return [f"{cls.get_type_name()} - {Kitchenware.get_type_name()}", "liquid"]

class Person:
	TYPE_NAME = "person"
	def __init__(self) -> None:
		self.items: list[MovableItem] = []
		self.token_name = "me"
		self.entity_id = EntityID(self.token_name, Person.TYPE_NAME)
	
	@staticmethod
	def get_in_hand_relation() -> str:
		return "in_hand"
	
	@staticmethod
	def get_in_hand_predicate(person_param: str, item_param: str) -> str:
		return f"{Person.get_in_hand_relation()} {item_param} {person_param}"
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [
			Predicate(Person.get_in_hand_relation(), ["?a - (either {})".format(" ".join([movable_type.get_type_name() for movable_type in movable_types])), f"?b - {Person.TYPE_NAME}"]),
		]
	
	def get_pddl_objects(self) -> list[str]:
		return [self.token_name + " - " + self.TYPE_NAME]
	
	def get_init_conditions(self) -> list[str]:
		return []
	
	def get_yaml_instance(self) -> Instance:
		return Instance(self.entity_id, [])
	
	def generate_goal(self, all_items: list[MovableItem]) -> Goal | None:
		return None
	
	def perform_action(self, all_items: list[MovableItem]) -> str | None:
		if len(self.items) >= 3:
			return None
		random.shuffle(all_items)
		for item in all_items:
			if item in self.items:
				continue
			assert isinstance(item.container, Container)
			action = "I picked up {}.".format(item.shortened_name)
			item.container.items.remove(item)
			self.items.append(item)
			item.container = self
			item.relative_location = None
			item.extra_location_info = {}
			return action

item_types: list[type[RoomItem]]
movable_types: list[type[MovableItem]]
stationary_types: list[type[StationaryItem]]

class Room(ABC):
	ROOM_PARAM = "?a"
	ITEM_PARAM = "?b"
	TYPE_NAME = "room"

	def __init__(self, name: str, token_name: str) -> None:
		self.name = name
		self.token_name = token_name
		self.entity_id = EntityID(token_name, "room")
		self.items: list[StationaryItem] = []
		self.queryable_items: list[Queryable] = []
		self.yaml_instance: Instance
	
	def add_item(self, item: StationaryItem) -> None:
		self.items.append(item)
		if isinstance(item, Queryable):
			self.queryable_items.append(item)
	
	@staticmethod
	@abstractmethod
	def generate_empty() -> Room | None:
		pass

	@classmethod
	def generate_outline(cls) -> tuple[Room, list[AccompanyingItem]] | None:
		room = cls.generate_empty()
		if room is None:
			return room

		attributes: list[Attribute] = []
		accompanying_items: list[AccompanyingItem] = []
		for item_type in stationary_types:
			if not cls.can_hold(item_type):
				continue
			item, additional = item_type.generate_instance(room)
			room.add_item(item)
			accompanying_items += additional
			attributes.append(Attribute(Room.get_in_room_relation(), item.entity_id))
					
		room.yaml_instance = Instance(room.entity_id, attributes)
		return room, accompanying_items

	def populate(self, movable_items: list[MovableItem]) -> str:
		random.shuffle(self.items)
		room_description = ""
		for i, item in enumerate(self.items):
			if isinstance(item, Container):
				item.populate(movable_items, max_allowed=5)
			room_description += "{}{} has a{} {}. ".format(self.name.capitalize(), "" if i == 0 else " also", "n" if item.name[0] in "aeiou" else "", item.name)
			room_description += item.get_description()
		return room_description
	
	def perform_action(self, person: Person) -> str | None:
		usable_items = self.items.copy()
		random.shuffle(usable_items)
		while len(usable_items) > 0:
			item = usable_items.pop()
			action = item.perform_action(person)
			if action is not None:
				return action
		return None
	
	def generate_goal(self, person: Person, all_items: list[MovableItem]) -> Goal | None:
		usable_items = self.items.copy()
		random.shuffle(usable_items)
		for item in usable_items:
			goal = item.generate_goal(person, all_items)
			if goal is not None:
				return goal
		return None
	
	def generate_query_answer(self) -> tuple[str, str]:
		return random.choice(self.queryable_items).generate_query_answer()
	
	@staticmethod
	@abstractmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		pass

	@classmethod
	def get_holdable_items(cls) -> list[type[StationaryItem]]:
		return [stationary_type for stationary_type in stationary_types if cls.can_hold(stationary_type)]

	@staticmethod
	def get_in_room_relation() -> str:
		return "room_has"
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		holdable_types = [item_type.get_type_name() for item_type in stationary_types]
		return [Predicate(Room.get_in_room_relation(), [Room.ROOM_PARAM + " - " + Room.TYPE_NAME, "{} - (either {})".format(Room.ITEM_PARAM, " ".join(holdable_types))])]
	
	def get_init_conditions(self) -> list[str]:
		init_conditions: list[str] = []
		for item in self.items:
			init_conditions += item.get_init_conditions()
		return init_conditions
	
	def get_pddl_objects(self) -> list[str]:
		objects: list[str] = [self.token_name + " - " + Room.TYPE_NAME]
		for item in self.items:
			objects += item.get_pddl_objects()
		return objects
	
	def get_knowledge_yaml(self, indent: int) -> str:
		yaml = self.yaml_instance.to_yaml(indent)
		for item in self.items:
			yaml += item.get_yaml_instance().to_yaml(indent)
		return yaml

class Kitchen(Room):
	generated = False
	@staticmethod
	def generate_empty() -> Kitchen | None:
		if Kitchen.generated:
			return None
		Kitchen.generated = True
		return Kitchen("the kitchen", "the_kitchen")
	
	@staticmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		return stationary_type in [Fridge, KitchenSink, Light]

class LivingRoom(Room):
	generated = False
	@staticmethod
	def generate_empty() -> LivingRoom | None:
		if LivingRoom.generated:
			return None
		LivingRoom.generated = True
		return LivingRoom("the living room", "the_living_room")
	
	@staticmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		return (not Kitchen.can_hold(stationary_type) and stationary_type != Sink) or stationary_type == Light

class Bedroom(Room):
	with open(os.path.join(DIR, "names.txt")) as f:	
		available_names = f.read().splitlines()
	
	@staticmethod
	def generate_empty() -> Bedroom | None:
		if len(Bedroom.available_names) == 0:
			return None
		name = Bedroom.available_names.pop(random.randrange(len(Bedroom.available_names)))
		return Bedroom(f"{name}'s bedroom", f"{name.lower()}_bedroom")
	
	@staticmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		return (not Kitchen.can_hold(stationary_type) and stationary_type != Sink) or stationary_type == Light

room_types: list[type[Room]]

class AgentConstants:
	@staticmethod
	def get_holding_predicate(item_param: str) -> str:
		return f"held_by_robot {item_param}"
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		type_list = "(either {})".format(" ".join([t.get_type_name() for t in movable_types]))
		return [Predicate(
			"held_by_robot",
			[f"?a - {type_list}"]
		)]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		type_list = "(either {})".format(" ".join([t.get_type_name() for t in movable_types]))
		in_person_hand_predicate = Person.get_in_hand_predicate("?b", "?a")
		return [
			Action(
				"pick_up",
				[f"?a - {type_list}"],
				["not (held_by_robot ?a)"],
				["held_by_robot ?a"]
			),
			Action(
				"hand_to_person",
				[f"?a - {type_list}", f"?b - {Person.TYPE_NAME}"],
				["held_by_robot ?a"],
				["not (held_by_robot ?a)", in_person_hand_predicate]
			),
			Action(
				"take_from_person",
				[f"?a - {type_list}", f"?b - {Person.TYPE_NAME}"],
				[in_person_hand_predicate],
				[f"not ({in_person_hand_predicate})", "held_by_robot ?a"]
			)
		]

class DatasetGenerator:
	MAX_ROOMS = 5
	MAX_ITEMS = 20

	def __init__(self, parent_dir: str, num_state_changes: int = 100, state_changes_per_query: int = 10, state_changes_per_goal: int = 20) -> None:
		self.num_state_changes = num_state_changes
		self.state_changes_per_query = state_changes_per_query
		self.state_changes_per_goal = state_changes_per_goal
		self.parent_dir = parent_dir
		self.rooms: list[Room] = []
		self.person = Person()
		self.description = ""

		self.movable_items: list[MovableItem] = []
		for movable_type in creatable_movable_types:
			count = 0
			while count < DatasetGenerator.MAX_ITEMS / len(creatable_movable_types):
				item = movable_type.generate_instance()
				if item is None:
					break
				self.movable_items.append(item)
				count += 1
		
		for room_type in room_types:
			count = 0
			while count < DatasetGenerator.MAX_ROOMS / len(room_types):
				pair = room_type.generate_outline()
				if pair is None:
					break
				room, additional = pair
				count += 1
				self.rooms.append(room)
				self.movable_items += additional
		
		remaining_movables = self.movable_items.copy()
		for room in self.rooms:
			self.description += room.populate(remaining_movables) + "\n\n"
		for item in remaining_movables:
			if isinstance(item, AccompanyingItem):
				raise Exception("Unable to include AccompanyingItem: ", item.name)
			self.movable_items.remove(item)
		random.shuffle(self.movable_items)
		random.shuffle(self.rooms)
	
	def generate_state_change(self) -> str:
		usable_rooms = self.rooms.copy()
		usable_movables = self.movable_items.copy()
		all_items = self.movable_items.copy()
		used_person = False
		while True:
			assert len(usable_rooms) > 0 or len(usable_movables) > 0 or (not used_person)
			choice = random.randrange(2 if used_person else 3)
			if len(usable_rooms) > 0 and choice == 0:
				action = usable_rooms.pop(random.randrange(len(usable_rooms))).perform_action(self.person)
				if action is not None:
					return action
			elif len(usable_movables) > 0 and choice == 1:
				action = usable_movables.pop(random.randrange(len(usable_movables))).perform_action(self.person)
				if action is not None:
					return action
			elif not used_person:
				action = self.person.perform_action(all_items)
				if action is not None:
					return action
				used_person = True

	
	def generate_goal(self) -> Goal:
		all_items = self.movable_items.copy()
		usable_rooms = self.rooms.copy()
		usable_movables = self.movable_items.copy()
		used_person = False
		while True:
			assert len(usable_rooms) > 0 or len(usable_movables) > 0 or (not used_person)
			choice = random.randrange(2 if used_person else 3)
			if len(usable_rooms) > 0 and choice == 0:
				goal = usable_rooms.pop(random.randrange(len(usable_rooms))).generate_goal(self.person, all_items)
				if goal is not None:
					return goal
			elif len(usable_movables) > 0 and choice == 1:
				goal = usable_movables.pop(random.randrange(len(usable_movables))).generate_goal(self.person, all_items)
				if goal is not None:
					return goal
			elif not used_person:
				goal = self.person.generate_goal(all_items)
				if goal is not None:
					return goal
				used_person = True
	
	def generate_query_answer(self) -> tuple[str, str]:
		if random.choice([True, False]):
			return random.choice(self.movable_items).generate_query_answer()
		return random.choice(self.rooms).generate_query_answer()
	
	def run(self) -> None:
		os.makedirs(self.parent_dir, exist_ok=True)
		with open(os.path.join(self.parent_dir, "initial_state.txt"), "w") as f:
			f.write(self.description)
		predicate_names, domain_pddl = self.generate_domain_pddl()
		with open(os.path.join(self.parent_dir, "predicate_names.txt"), "w") as f:
			f.write("\n".join(predicate_names))
		with open(os.path.join(self.parent_dir, "domain.pddl"), "w") as f:
			f.write(domain_pddl)
		with open(os.path.join(self.parent_dir, "problem.pddl"), "w") as f:
			f.write(self.generate_problem_pddl())
		with open(os.path.join(self.parent_dir, "knowledge.yaml"), "w") as f:
			f.write(self.generate_knowledge_yaml())
		
		time_step = 0
		for i in range(self.num_state_changes):
			curr_dir = os.path.join(self.parent_dir, f"time_{time_step:04d}_state_change")
			os.makedirs(curr_dir, exist_ok=True)
			with open(os.path.join(curr_dir, "state_change.txt"), "w") as f:
				f.write(self.generate_state_change())
			with open(os.path.join(curr_dir, "problem.pddl"), "w") as f:
				f.write(self.generate_problem_pddl())
			with open(os.path.join(curr_dir, "knowledge.yaml"), "w") as f:
				f.write(self.generate_knowledge_yaml())
			time_step += 1
			if (i + 1) % self.state_changes_per_query == 0:
				curr_dir = os.path.join(self.parent_dir, f"time_{time_step:04d}_query")
				os.makedirs(curr_dir, exist_ok=True)
				query, true_answer = self.generate_query_answer()
				with open(os.path.join(curr_dir, "query.txt"), "w") as f:
					f.write(query)
				with open(os.path.join(curr_dir, "answer.txt"), "w") as f:
					f.write(true_answer)
				time_step += 1
			if (i + 1) % self.state_changes_per_goal == 0:
				curr_dir = os.path.join(self.parent_dir, f"time_{time_step:04d}_goal")
				os.makedirs(curr_dir, exist_ok=True)
				problem_pddl = self.generate_problem_pddl(with_goal=True)
				goal = self.generate_goal()
				with open(os.path.join(curr_dir, "goal.txt"), "w") as f:
					f.write(goal.description)
				with open(os.path.join(curr_dir, "problem.pddl"), "w") as f:
					f.write(problem_pddl.format(str(goal)))
				with open(os.path.join(curr_dir, "knowledge.yaml"), "w") as f:
					f.write(self.generate_knowledge_yaml())
				time_step += 1
	
	@staticmethod
	def generate_domain_pddl() -> tuple[list[str], str]:
		predicates: list[Predicate] = Person.get_pddl_domain_predicates() + Room.get_pddl_domain_predicates()
		actions: list[Action] = []
		required_types: list[str] = [Person.TYPE_NAME, Room.TYPE_NAME]
		for item_type in item_types:
			predicates += item_type.get_pddl_domain_predicates()
			actions += item_type.get_pddl_domain_actions()
			required_types += item_type.get_required_types()
		
		required_types = sorted(required_types, key=len)

		predicates += AgentConstants.get_pddl_domain_predicates()
		actions += AgentConstants.get_pddl_domain_actions()

		predicate_names = [predicate.name for predicate in predicates]

		formatted_predicates = [str(predicate) for predicate in predicates]
		formatted_actions = [str(action) for action in actions]

		return predicate_names, \
				"(define (domain simulation)\n" \
					+ "\t(:requirements :typing :negative-preconditions)\n" \
					+ "\t(:types\n" \
						+ "\t\t{}\n".format("\n\t\t".join(required_types)) \
					+ "\t)\n" \
					+ "\t(:predicates\n" \
						+ "\t\t{}\n".format("\n\t\t".join(formatted_predicates)) \
					+ "\t)\n\n" \
					+ "{}".format("\n".join(formatted_actions)) \
				+ ")\n"
	
	def generate_problem_pddl(self, with_goal: bool = False) -> str:
		objects: list[str] = self.person.get_pddl_objects()
		init_conditions: list[str] = self.person.get_init_conditions()
		for room in self.rooms:
			objects += room.get_pddl_objects()
			init_conditions += room.get_init_conditions()
		
		for item in self.movable_items:
			objects += item.get_pddl_objects()
			init_conditions += item.get_init_conditions()
		
		for entity in static_entities:
			objects.append(f"{entity.entity_id.name} - {entity.entity_id.concept}")
		
		return "(define (problem simulation-a)\n" \
					+ "\t(:domain simulation)\n" \
					+ "\t(:objects\n" \
						+ "\t\t{}\n".format("\n\t\t".join(objects)) \
					+ "\t)\n" \
					+ "\t(:init\n" \
						+ "\t\t({})\n".format(")\n\t\t(".join(init_conditions)) \
					+ "\t)\n" \
					+ ("{}" if with_goal else "") \
				+ ")\n"
	
	def generate_knowledge_yaml(self) -> str:
		yaml = "version: 1\nentities:\n"
		for room in self.rooms:
			yaml += room.get_knowledge_yaml(1)
		for item in self.movable_items:
			yaml += item.get_yaml_instance().to_yaml(1)
		for item in static_entities:
			yaml += item.to_yaml(1)
		yaml += self.person.get_yaml_instance().to_yaml(1)
		return yaml


class Dataset:
	def __init__(self, parent_dir: str) -> None:
		self.domain_path = os.path.join(parent_dir, "domain.pddl")
		self.initial_knowledge_path = os.path.join(parent_dir, "knowledge.yaml")
		with open(os.path.join(parent_dir, "initial_state.txt")) as f:
			self.initial_state = f.read()
		with open(os.path.join(parent_dir, "predicate_names.txt")) as f:
			self.predicate_names = f.read().splitlines()
		with open(self.domain_path) as f:
			self.domain_pddl = f.read()
		with open(os.path.join(parent_dir, "problem.pddl")) as f:
			self.initial_problem_pddl = f.read()
		with open(self.initial_knowledge_path) as f:
			self.initial_knowledge_yaml = f.read()
		
		time_steps = os.listdir(parent_dir)
		time_steps.remove("initial_state.txt")
		time_steps.remove("predicate_names.txt")
		time_steps.remove("domain.pddl")
		time_steps.remove("problem.pddl")
		time_steps.remove("knowledge.yaml")
		time_steps.sort()

		self.num_time_steps = len(time_steps)
		self.time_steps: list[dict[str, Any]] = []

		for i, time_step in enumerate(time_steps):
			curr_dir = os.path.join(parent_dir, time_step)
			curr_data: dict[str, Any] = {"time" : i}
			if time_step.endswith("query"):
				curr_data["type"] = "query"
				with open(os.path.join(curr_dir, "query.txt")) as f:
					curr_data["query"] = f.read()
				with open(os.path.join(curr_dir, "answer.txt")) as f:
					curr_data["answer"] = f.read()
			elif time_step.endswith("state_change"):
				curr_data["type"] = "state_change"
				with open(os.path.join(curr_dir, "state_change.txt")) as f:
					curr_data["state_change"] = f.read()
				curr_data["problem_path"] = os.path.join(curr_dir, "problem.pddl")
				with open(curr_data["problem_path"]) as f:
					curr_data["problem_pddl"] = f.read()
				curr_data["knowledge_path"] = os.path.join(curr_dir, "knowledge.yaml")
				with open(curr_data["knowledge_path"]) as f:
					curr_data["knowledge_yaml"] = f.read()
			elif time_step.endswith("goal"):
				curr_data["type"] = "goal"
				with open(os.path.join(curr_dir, "goal.txt")) as f:
					curr_data["goal"] = f.read()
				curr_data["problem_path"] = os.path.join(curr_dir, "problem.pddl")
				with open(curr_data["problem_path"]) as f:
					curr_data["problem_pddl"] = f.read()
				curr_data["knowledge_path"] = os.path.join(curr_dir, "knowledge.yaml")
				with open(curr_data["knowledge_path"]) as f:
					curr_data["knowledge_yaml"] = f.read()
			else:
				raise Exception("Invalid dataset directory:", time_step)
			self.time_steps.append(curr_data)
		
		self.curr_time_step = -1
	
	def __iter__(self):
		return self
	
	def __next__(self):
		self.curr_time_step += 1
		if self.curr_time_step >= self.num_time_steps:
			raise StopIteration
		return self.time_steps[self.curr_time_step]

T = TypeVar('T')
def get_concrete_subtypes(initial_type: type[T]) -> list[type[T]]:
	found_types: list[type[initial_type]] = [initial_type]
	concrete_subtypes: set[type[initial_type]] = set()
	while len(found_types) > 0:
		curr_type = found_types.pop()
		if not isabstract(curr_type):
			concrete_subtypes.add(curr_type)
		found_types.extend(curr_type.__subclasses__())
	return list(concrete_subtypes)

item_types = get_concrete_subtypes(RoomItem)
movable_types = get_concrete_subtypes(MovableItem)
creatable_movable_types = [movable_type for movable_type in movable_types if not issubclass(movable_type, AccompanyingItem)]
stationary_types = get_concrete_subtypes(StationaryItem)
room_types = get_concrete_subtypes(Room)
static_entities: list[Instance] = []
for item_type in item_types:
	static_entities += item_type.get_static_entities()

if __name__ == "__main__":
	generator = DatasetGenerator("test", num_state_changes=50, state_changes_per_query=50, state_changes_per_goal=1)
	generator.run()