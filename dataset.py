from __future__ import annotations
from abc import abstractmethod, ABC
from typing import Any
import random
from typing import TypeVar
from inspect import isabstract
import re
import os

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
	def __init__(self, name: str, pddl_name: str, yaml_name: str) -> None:
		self.name = name
		self.pddl_name = pddl_name
		self.entity_id = EntityID(yaml_name, type(self).__name__.lower())

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
		return [cls.get_type_name()]
	
	@abstractmethod
	def get_init_conditions(self) -> list[str]:
		pass

	def get_pddl_objects(self) -> list[str]:
		return [self.pddl_name + " - " + self.get_type_name()]
	
	@staticmethod
	def get_static_pddl_objects() -> list[str]:
		return []
	
	@abstractmethod
	def get_yaml_attributes(self) -> list[Attribute]:
		pass
	
	def get_yaml_instance(self) -> Instance:
		return Instance(self.entity_id, self.get_yaml_attributes())

class Queryable:
	@abstractmethod
	def generate_query_answer(self) -> tuple[str, str]:
		pass

class StationaryItem(RoomItem):
	def __init__(self, name: str, parent: Room) -> None:
		suffix = re.sub(r"[^a-zA-Z0-9]+", "-", name).lower()
		pddl_name = parent.pddl_name + "-" + suffix
		yaml_name = parent.entity_id.name + "_" + suffix.replace("-", "_")
		super().__init__(name, pddl_name, yaml_name)
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
		return [self.parent.get_in_room_predicate(self.parent.pddl_name, self.pddl_name)]
	
	def get_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("in_room", self.parent.entity_id)]

class MovableItem(RoomItem, Queryable):
	def __init__(self, name: str, pddl_name: str, yaml_name: str, shortened_name: str, use_default_article: bool = True) -> None:
		super().__init__(name, pddl_name, yaml_name)
		self.shortened_name = shortened_name
		self.container: Container | Person
		self.relative_location: str | None = None
		self.extra_location_info: dict[Any, Any] = {}
		self.use_default_article = use_default_article
	
	def generate_query_answer(self) -> tuple[str, str]:
		query = f"Where is the {self.shortened_name}?"
		if isinstance(self.container, Person):
			answer = f"You are holding the {self.shortened_name}."
		else:
			answer = f"The {self.shortened_name} is {self.relative_location} the {self.container.get_full_name_with_room()}."
		return query, answer
	
	def perform_action(self, person: Person) -> str | None:
		if person.item is not None:
			return None
		assert isinstance(self.container, Container)
		action = "I picked up {}{} {} the {}.".format("the " if self.use_default_article else "", self.shortened_name, self.relative_location, self.container.get_full_name_with_room())
		person.item = self
		self.container.items.remove(self)
		self.container = person
		self.relative_location = None
		return action

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
			return [Person.get_in_hand_predicate(self.container.pddl_name, self.pddl_name)]
		return [self.container.get_contains_predicate(self.container.pddl_name, self.pddl_name, **self.extra_location_info)]
	
	def get_yaml_attributes(self) -> list[Attribute]:
		attributes = [Attribute("held_by" if isinstance(self.container, Person) else "contained_by", self.container.entity_id)]
		if "extra_attributes" in self.extra_location_info.keys():
			extras = self.extra_location_info.get("extra_attributes")
			assert isinstance(extras, list)
			attributes += extras
		return attributes

class AccompanyingItem(MovableItem):
	def __init__(self, name: str, pddl_name: str, yaml_name: str, shortened_name: str, use_default_article: bool = True) -> None:
		super().__init__(name, pddl_name, yaml_name, shortened_name, use_default_article)

class Container(StationaryItem):
	CONTAINER_PARAM = "?a"
	ITEM_PARAM = "?b"
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
		if person.item is None or not self.can_hold(type(person.item)):
			return None
		item = person.item
		person.item = None
		self.items.append(item)
		item.container = self
		item.relative_location, item.extra_location_info = self.generate_relative_location()
		return f"I placed the {item.shortened_name} I was holding {item.relative_location} the {self.get_full_name_with_room()}."
	
	@classmethod
	def get_contains_predicate_name(cls) -> str:
		return f"{cls.get_type_name()}-contains"

	@classmethod
	def get_place_action_name(cls) -> str:
		return f"place-among-{cls.get_type_name()}"

	@classmethod
	def get_remove_action_name(cls) -> str:
		return f"remove-from-{cls.get_type_name()}"
	
	@classmethod
	def get_contains_predicate(cls, container_param: str, item_param: str, **kwargs) -> str:
		return f"{cls.get_contains_predicate_name()} {container_param} {item_param}"

	@classmethod
	def get_default_parameter_list(cls) -> list[str]:
		holdable_types = [holdable_type.get_type_name() for holdable_type in cls.get_holdable_types()]
		return [f"{cls.CONTAINER_PARAM} - {cls.get_type_name()}", "{} - (either {})".format(cls.ITEM_PARAM, " ".join(holdable_types))]
	
	@classmethod
	def get_pddl_domain_predicates(cls) -> list[Predicate]:
		return [Predicate(cls.get_contains_predicate_name(), cls.get_default_parameter_list())]
	
	@classmethod
	def get_place_action(cls) -> Action:
		param_list = cls.get_default_parameter_list()
		param_list.append(f"{cls.PERSON_PARAM} - {Person.TYPE_NAME}")
		in_hand_predicate = Person.get_in_hand_predicate(cls.PERSON_PARAM, cls.ITEM_PARAM)
		empty_hand_predicate = Person.get_empty_hand_predicate(cls.PERSON_PARAM)
		contains_predicate = cls.get_contains_predicate(cls.CONTAINER_PARAM, cls.ITEM_PARAM, **cls.EXTRA_INFO)

		place_preconditions = [in_hand_predicate]
		place_effects = [
			f"not ({in_hand_predicate})",
			empty_hand_predicate,
			contains_predicate
		]
		return Action(cls.get_place_action_name(), param_list, place_preconditions, place_effects)
	
	@classmethod
	def get_remove_action(cls) -> Action:
		param_list = cls.get_default_parameter_list()
		param_list.append(f"{cls.PERSON_PARAM} - {Person.TYPE_NAME}")
		in_hand_predicate = Person.get_in_hand_predicate(cls.PERSON_PARAM, cls.ITEM_PARAM)
		empty_hand_predicate = Person.get_empty_hand_predicate(cls.PERSON_PARAM)
		contains_predicate = cls.get_contains_predicate(cls.CONTAINER_PARAM, cls.ITEM_PARAM, **cls.EXTRA_INFO)

		remove_preconditions = [
			contains_predicate,
			empty_hand_predicate
		]
		remove_effects = [
			f"not ({contains_predicate})",
			f"not ({empty_hand_predicate})",
			in_hand_predicate
		]
		return Action(cls.get_remove_action_name(), param_list, remove_preconditions, remove_effects)
	
	@classmethod
	def get_pddl_domain_actions(cls) -> list[Action]:
		return [cls.get_place_action(), cls.get_remove_action()]
	
	def get_yaml_attributes(self) -> list[Attribute]:
		attributes = StationaryItem.get_yaml_attributes(self)
		for item in self.items:
			attributes.append(Attribute("has_object", item.entity_id))
		return attributes

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
	LEVEL_TYPE = "level"
	EXTRA_INFO: dict[str, Any] = {"pddl_level" : LEVEL_PARAM}

	@staticmethod
	def get_level_name(level: int) -> str:
		return "level-" + str(level)
	
	LEVEL_OBJECTS: list[str] = []
	for i in range(MAX_LEVELS):
		LEVEL_OBJECTS.append(get_level_name.__func__(i + 1) + " - " + LEVEL_TYPE)

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
			items_by_level[item.extra_location_info["level"]].append(item)
		description = f"The shelf has {self.levels} levels. "
		for level, item_list in items_by_level.items():
			if len(item_list) == 0:
				continue
			description += f"The {Shelf.integer_to_ordinal(level)} level of the shelf has {Shelf.get_item_list_description(item_list)}. "
		return description
	
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		level = random.randrange(self.levels) + 1
		return f"on the {Shelf.integer_to_ordinal(level)} level of", {"level" : level, "pddl_level": self.get_level_name(level), "extra_attributes": [Attribute("on_shelf_level", level)]}

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
		predicates.append(Predicate("shelf-has-level", [f"?a - {cls.get_type_name()}", f"?b - {cls.LEVEL_TYPE}"]))
		return predicates
	
	@classmethod
	def get_place_action(cls) -> Action:
		place = super().get_place_action()
		place.preconditions.append(f"shelf-has-level {super().CONTAINER_PARAM} {cls.LEVEL_PARAM}")
		return place
	
	@classmethod
	def get_default_parameter_list(cls) -> list[str]:
		param_list = super().get_default_parameter_list()
		param_list.append(f"{cls.LEVEL_PARAM} - {cls.LEVEL_TYPE}")
		return param_list
	
	@classmethod
	def get_contains_predicate(cls, container_param: str, item_param: str, **kwargs) -> str:
		return super().get_contains_predicate(container_param, item_param, **kwargs) + " " + kwargs["pddl_level"]
	
	@classmethod
	def get_required_types(cls) -> list[str]:
		types = super().get_required_types()
		types.append(cls.LEVEL_TYPE)
		return types
	
	def get_init_conditions(self) -> list[str]:
		conditions = super().get_init_conditions()
		for i in range(self.levels):
			conditions.append(f"shelf-has-level {self.pddl_name} {self.get_level_name(i + 1)}")
		return conditions
	
	def get_yaml_attributes(self) -> list[Attribute]:
		attributes = Container.get_yaml_attributes(self)
		attributes.append(Attribute("num_levels", self.levels))
		return attributes
	
	@staticmethod
	def get_static_pddl_objects() -> list[str]:
		return Shelf.LEVEL_OBJECTS

class Fridge(Container):
	@staticmethod
	def can_hold(item_type: type[MovableItem]) -> bool:
		return issubclass(item_type, Food)
	
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		return "inside", {}

	@staticmethod
	def generate_instance(parent: Room) -> tuple[Fridge, list[AccompanyingItem]]:
		return Fridge("fridge", parent), []

class Sink(InteractableContainer):
	def __init__(self, name: str, parent: Room, faucet_on: bool) -> None:
		super().__init__(name, parent)
		self.faucet_on = faucet_on

	@staticmethod
	def can_hold(item_type: type[MovableItem]) -> bool:
		return issubclass(item_type, Kitchenware)
	
	def generate_relative_location(self) -> tuple[str, dict[Any, Any]]:
		return "in", {}

	def interact(self, person: Person) -> str | None:
		self.faucet_on = not self.faucet_on
		return "I turned {} the faucet of the {}.".format("on" if self.faucet_on else "off", self.get_full_name_with_room())
	
	def generate_query_answer(self) -> tuple[str, str]:
		return f"Is the faucet of the {self.get_full_name_with_room()} on or off?", "The faucet is {}.".format("on" if self.faucet_on else "off")
	
	def get_special_init_conditions(self) -> list[str]:
		if self.faucet_on:
			return ["faucet-on " + self.pddl_name]
		return []
	
	def get_interactable_description(self) -> str:
		return "The sink has a faucet that can be turned on and off. It is currently {}. ".format("on" if self.faucet_on else "off")
	
	@staticmethod
	def get_special_domain_predicates() -> list[Predicate]:
		return [Predicate("faucet-on", ["?a - " + Sink.get_type_name()])]
	
	@staticmethod
	def get_special_domain_actions() -> list[Action]:
		return [
			Action("turn-on-faucet", ["?a - " + Sink.get_type_name()], ["not (faucet-on ?a)"], ["faucet-on ?a"]),
			Action("turn-off-faucet", ["?a - " + Sink.get_type_name()], ["faucet-on ?a"], ["not (faucet-on ?a)"])
		]

	@staticmethod
	def generate_instance(parent: Room) -> tuple[Sink, list[AccompanyingItem]]:
		return Sink("sink", parent, random.choice([True, False])), []
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("is_faucet_on", self.faucet_on)]

class Book(MovableItem):
	with open("book_titles.txt") as f:	
		available_titles = f.read().splitlines()

	def __init__(self, title: str) -> None:
		prefix = re.sub(r"[^a-zA-Z0-9]+", "-", title).lower()
		super().__init__(f'book called "{title}"', prefix + "-book", prefix.replace("-", "_") + "_book", f'"{title}" book')

	@staticmethod
	def generate_instance() -> Book | None:
		if len(Book.available_titles) == 0:
			return None
		idx = random.randrange(len(Book.available_titles))
		return Book(Book.available_titles.pop(idx))

class Pen(MovableItem):
	with open("colors.txt") as f:	
		available_colors = f.read().lower().splitlines()

	def __init__(self, color: str) -> None:
		super().__init__(f"{color} pen", color + "-pen", color + "_pen", f"{color} pen")
	
	@staticmethod
	def generate_instance() -> Pen | None:
		if len(Pen.available_colors) == 0:
			return None
		idx = random.randrange(len(Pen.available_colors))
		return Pen(Pen.available_colors.pop(idx))

class Singleton(MovableItem):
	def __init__(self, name: str) -> None:
		pddl_name = re.sub(r"[^a-zA-Z0-9]+", "-", name).lower()
		super().__init__(name, pddl_name, pddl_name.replace("-", "_"), name)
	
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

class Food(Singleton):
	with open("foods.txt") as f:
		available_foods = f.read().lower().splitlines()
	
	@staticmethod
	def get_available_names() -> list[str]:
		return Food.available_foods

class Kitchenware(Singleton):
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
		return [Predicate("window-open", ["?a - window"])]

	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("open-window", ["?a - window"], ["not (window-open ?a)"], ["window-open ?a"]),
			Action("close-window", ["?a - window"], ["window-open ?a"], ["not (window-open ?a)"])
		]
	
	def get_special_init_conditions(self) -> list[str]:
		if self.open:
			return ["window-open " + self.pddl_name]
		return []
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("is_window_open", self.open)]

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
		return [Predicate("light-on", ["?a - " + Light.get_type_name()])]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("turn-on-light", ["?a - " + Light.get_type_name()], ["not (light-on ?a)"], ["light-on ?a"]),
			Action("turn-off-light", ["?a - " + Light.get_type_name()], ["light-on ?a"], ["not (light-on ?a)"])
		]
	
	def get_special_init_conditions(self) -> list[str]:
		if self.on:
			return ["light-on " + self.pddl_name]
		return []
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("is_light_on", self.on)]

class TV(StationaryInteractable):
	class Channel:
		TYPE_NAME = "channel"
		def __init__(self, name: str) -> None:
			self.name = name
			self.pddl_name = re.sub(r"[^a-zA-Z0-9]+", "-", name).lower()
			self.entity_id = EntityID(self.pddl_name.replace("-", "_"), "tv_channel")

	CHANNELS = [
		Channel("the Discovery Channel"),
		Channel("Cartoon Network"),
		Channel("NBC"),
		Channel("CNN"),
		Channel("Fox News"),
		Channel("ESPN")
	]
	CHANNEL_OBJECTS = []
	for channel in CHANNELS:
		CHANNEL_OBJECTS.append(channel.pddl_name + " - " + Channel.TYPE_NAME)

	def __init__(self, parent: Room, on: bool, curr_channel: Channel) -> None:
		super().__init__("TV", parent)
		self.on = on
		self.curr_channel = curr_channel
	
	def generate_query_answer(self) -> tuple[str, str]:
		query = f"Is the TV in {self.parent.name} on or off? If it's on, what channel is it playing?"
		answer = "The TV is {}{}.".format("on" if self.on else "off", f" and is playing {self.curr_channel.name}" if self.on else "")
		return query, answer
	
	def perform_action(self, person: Person) -> str | None:
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
		return TV(parent, random.choice([True, False]), random.choice(TV.CHANNELS)), []
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [Predicate("tv-on", ["?a - tv"]), Predicate("tv-playing-channel", ["?a - tv", "?b - channel"])]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [
			Action("turn-tv-on", ["?a - tv", "?b - channel"], ["not (tv-on ?a)"], ["tv-on ?a", "tv-playing-channel ?a ?b"]),
			Action("turn-tv-off", ["?a - tv", "?b - channel"], ["tv-on ?a", "tv-playing-channel ?a ?b"], ["not (tv-on ?a)", "not (tv-playing-channel ?a ?b)"]),
			Action("switch-tv-channel", ["?a - tv", "?b - channel", "?c - channel"], ["tv-playing-channel ?a ?b"], ["tv-playing-channel ?a ?c", "not (tv-playing-channel ?a ?b)"])
		]
	
	@classmethod
	def get_required_types(cls) -> list[str]:
		types = super().get_required_types()
		types.append(cls.Channel.TYPE_NAME)
		return types
	
	def get_special_init_conditions(self) -> list[str]:
		if self.on:
			return ["tv-on " + self.pddl_name, f"tv-playing-channel {self.pddl_name} {self.curr_channel.pddl_name}"]
		return []
	
	@staticmethod
	def get_static_pddl_objects() -> list[str]:
		return TV.CHANNEL_OBJECTS
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		attributes = [Attribute("is_tv_on", self.on)]
		if (self.on):
			attributes.append(Attribute("channel_playing", self.channel.entity_id))
		return attributes

class Phone(MovableInteractable):
	with open("names.txt") as f:	
		available_names = f.read().splitlines()

	def __init__(self, owner: str) -> None:
		super().__init__(f"phone that belongs to {owner}", owner.lower() + "-phone", owner.lower() + "_phone", f"{owner}'s phone", use_default_article=False)
		self.ringing = False
	
	def get_special_init_conditions(self) -> list[str]:
		if self.ringing:
			return ["phone-ringing " + self.pddl_name]
		return []
	
	def generate_interactable_qa(self) -> tuple[str, str]:
		return f"Is {self.shortened_name} ringing?", "Yes." if self.ringing else "No."
	
	def interact(self, person: Person) -> str | None:
		self.ringing = not self.ringing
		return "{} {} ringing.".format(self.shortened_name, "started" if self.ringing else "stopped")
	
	@staticmethod
	def get_pddl_domain_predicates() -> list[Predicate]:
		return [Predicate("is-ringing", ["?a - " + Phone.get_type_name()])]
	
	@staticmethod
	def get_pddl_domain_actions() -> list[Action]:
		return [Action("answer-phone", ["?a - " + Phone.get_type_name()], ["is-ringing ?a"], ["not (is-ringing ?a)"])]

	@staticmethod
	def generate_instance() -> Phone | None:
		if len(Phone.available_names) == 0:
			return None
		return Phone(Phone.available_names.pop(random.randrange(len(Phone.available_names))))
	
	def get_special_yaml_attributes(self) -> list[Attribute]:
		return [Attribute("is_phone_ringing", self.ringing)]

class Person:
	TYPE_NAME = "person"
	def __init__(self) -> None:
		self.item: MovableItem | None = None
		self.pddl_name = "me"
		self.entity_id = EntityID("person_1", "person")
	
	@staticmethod
	def get_in_hand_predicate(person_param: str, item_param: str):
		return f"in-hand {person_param} {item_param}"
	
	@staticmethod
	def get_empty_hand_predicate(person_param):
		return f"hand-empty {person_param}"
	
	@staticmethod
	def get_pddl_domain_predicates():
		return [
			Predicate("in-hand", [f"?a - {Person.TYPE_NAME}", "?b - (either {})".format(" ".join([movable_type.get_type_name() for movable_type in movable_types]))]),
			Predicate("hand-empty", [f"?a - {Person.TYPE_NAME}"])
		]
	
	def get_pddl_objects(self) -> list[str]:
		return [self.pddl_name + " - " + self.TYPE_NAME]
	
	def get_init_conditions(self) -> list[str]:
		if self.item is None:
			return [self.get_empty_hand_predicate(self.pddl_name)]
		return []
	
	def get_yaml_instance(self) -> Instance:
		attributes: list[Attribute] = []
		if self.item is not None:
			attributes.append(Attribute("is_holding", self.item.entity_id))
		return Instance(self.entity_id, attributes)

item_types: list[type[RoomItem]]
movable_types: list[type[MovableItem]]
stationary_types: list[type[StationaryItem]]

class Room(ABC):
	ROOM_PARAM = "?a"
	ITEM_PARAM = "?b"

	def __init__(self, name: str, pddl_name: str, yaml_name: str) -> None:
		self.name = name
		self.pddl_name = pddl_name
		self.entity_id = EntityID(yaml_name, type(self).__name__.lower())
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
			attributes.append(Attribute("has", item.entity_id))
					
		room.yaml_instance = Instance(room.entity_id, attributes)
		return room, accompanying_items
		

	def populate(self, movable_items: list[MovableItem]) -> str:
		random.shuffle(self.items)
		room_description = ""
		for i, item in enumerate(self.items):
			if isinstance(item, Container):
				item.populate(movable_items, max_allowed=2)
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
	
	def generate_query_answer(self) -> tuple[str, str]:
		return random.choice(self.queryable_items).generate_query_answer()
	
	@staticmethod
	@abstractmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		pass

	@classmethod
	def get_holdable_items(cls) -> list[type[StationaryItem]]:
		return [stationary_type for stationary_type in stationary_types if cls.can_hold(stationary_type)]
	
	@classmethod
	def get_in_room_predicate_name(cls) -> str:
		return "in-" + cls.get_type_name()
	
	@classmethod
	def get_in_room_predicate(cls, room_param: str, container_param: str) -> str:
		return f"{cls.get_in_room_predicate_name()} {room_param} {container_param}"
	
	@classmethod
	def get_pddl_domain_predicates(cls) -> list[Predicate]:
		holdable_types = [item_type.get_type_name() for item_type in cls.get_holdable_items()]
		return [Predicate(cls.get_in_room_predicate_name(), [cls.ROOM_PARAM + " - " + cls.get_type_name(), "{} - (either {})".format(cls.ITEM_PARAM, " ".join(holdable_types))])]
	
	@classmethod
	def get_type_name(cls) -> str:
		return cls.__name__.lower()

	@classmethod
	def get_required_types(cls) -> list[str]:
		return [cls.get_type_name()]
	
	def get_init_conditions(self) -> list[str]:
		init_conditions: list[str] = []
		for item in self.items:
			init_conditions += item.get_init_conditions()
		return init_conditions
	
	def get_pddl_objects(self) -> list[str]:
		objects: list[str] = [self.pddl_name + " - " + self.get_type_name()]
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
		return Kitchen("the kitchen", "kitchen", "the_kitchen")
	
	@staticmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		return stationary_type in [Fridge, Sink, Light]

class LivingRoom(Room):
	generated = False
	@staticmethod
	def generate_empty() -> LivingRoom | None:
		if LivingRoom.generated:
			return None
		LivingRoom.generated = True
		return LivingRoom("the living room", "living-room", "the_living_room")
	
	@staticmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		return not Kitchen.can_hold(stationary_type) or stationary_type == Light

class Bedroom(Room):
	with open("names.txt") as f:	
		available_names = f.read().splitlines()
	
	@staticmethod
	def generate_empty() -> Bedroom | None:
		if len(Bedroom.available_names) == 0:
			return None
		name = Bedroom.available_names.pop(random.randrange(len(Bedroom.available_names)))
		return Bedroom(f"{name}'s bedroom", f"{name.lower()}-bedroom", f"{name.lower()}_bedroom")
	
	@staticmethod
	def can_hold(stationary_type: type[StationaryItem]) -> bool:
		return not Kitchen.can_hold(stationary_type) or stationary_type == Light

room_types: list[type[Room]]

class DatasetGenerator:
	MAX_ROOMS = 5
	MAX_ITEMS = 20

	def __init__(self, parent_dir: str, num_queries: int = 100, state_changes_per_query: int = 10) -> None:
		self.num_queries = num_queries
		self.state_changes_per_query = state_changes_per_query
		self.parent_dir = parent_dir
		self.rooms: list[Room] = []
		self.person = Person()
		self.description = ""

		self.movable_items: list[MovableItem] = []
		for movable_type in movable_types:
			count = 0
			while count < DatasetGenerator.MAX_ITEMS / len(movable_types):
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
		while True:
			assert len(usable_rooms) > 0 or len(usable_movables) > 0
			if len(usable_rooms) > 0 and random.choice([True, False]):
				action = usable_rooms.pop(random.randrange(len(usable_rooms))).perform_action(self.person)
				if action is not None:
					return action
			if len(usable_movables) > 0:
				action = usable_movables.pop(random.randrange(len(usable_movables))).perform_action(self.person)
				if action is not None:
					return action
	
	def generate_query_answer(self) -> tuple[str, str]:
		if random.choice([True, False]):
			return random.choice(self.movable_items).generate_query_answer()
		return random.choice(self.rooms).generate_query_answer()
	
	def run(self) -> None:
		os.makedirs(self.parent_dir, exist_ok=True)
		with open(os.path.join(self.parent_dir, "initial_state.txt"), "w") as f:
			f.write(self.description)
		with open(os.path.join(self.parent_dir, "domain.pddl"), "w") as f:
			f.write(self.generate_domain_pddl())
		with open(os.path.join(self.parent_dir, "problem.pddl"), "w") as f:
			f.write(self.generate_problem_pddl())
		with open(os.path.join(self.parent_dir, "knowledge.yaml"), "w") as f:
			f.write(self.generate_knowledge_yaml())
		
		time_step = 0
		for _ in range(self.num_queries):
			for _ in range(self.state_changes_per_query):
				curr_dir = os.path.join(self.parent_dir, f"time_{time_step:04d}_state_change")
				os.makedirs(curr_dir, exist_ok=True)
				with open(os.path.join(curr_dir, "state_change.txt"), "w") as f:
					f.write(self.generate_state_change())
				with open(os.path.join(curr_dir, "problem.pddl"), "w") as f:
					f.write(self.generate_problem_pddl())
				with open(os.path.join(curr_dir, "knowledge.yaml"), "w") as f:
					f.write(self.generate_knowledge_yaml())
				time_step += 1
			curr_dir = os.path.join(self.parent_dir, f"time_{time_step:04d}_query")
			os.makedirs(curr_dir, exist_ok=True)
			query, true_answer = self.generate_query_answer()
			with open(os.path.join(curr_dir, "query.txt"), "w") as f:
				f.write(query)
			with open(os.path.join(curr_dir, "answer.txt"), "w") as f:
				f.write(true_answer)
			time_step += 1
	
	@staticmethod
	def generate_domain_pddl() -> str:
		predicates: list[Predicate] = Person.get_pddl_domain_predicates()
		actions: list[Action] = []
		required_types: list[str] = [Person.TYPE_NAME]
		for item_type in item_types:
			predicates += item_type.get_pddl_domain_predicates()
			actions += item_type.get_pddl_domain_actions()
			required_types += item_type.get_required_types()
		
		for room_type in room_types:
			predicates += room_type.get_pddl_domain_predicates()
			required_types += room_type.get_required_types()

		formatted_predicates = [str(predicate) for predicate in predicates]
		formatted_actions = [str(action) for action in actions]

		return "(define (domain simulation)\n" \
					+ "\t(:requirements :typing :negative-preconditions)\n" \
					+ "\t(:types\n" \
						+ "\t\t{}\n".format("\n\t\t".join(required_types)) \
					+ "\t)\n" \
					+ "\t(:predicates\n" \
						+ "\t\t{}\n".format("\n\t\t".join(formatted_predicates)) \
					+ "\t)\n\n" \
					+ "{}".format("\n".join(formatted_actions)) \
				+ ")\n"
	
	def generate_problem_pddl(self) -> str:
		objects: list[str] = self.person.get_pddl_objects()
		init_conditions: list[str] = self.person.get_init_conditions()
		for room in self.rooms:
			objects += room.get_pddl_objects()
			init_conditions += room.get_init_conditions()
		
		for item in self.movable_items:
			objects += item.get_pddl_objects()
			init_conditions += item.get_init_conditions()
		
		for item_type in item_types:
			objects += item_type.get_static_pddl_objects()
		
		return "(define (problem simulation-a)\n" \
					+ "\t(:domain simulation)\n" \
					+ "\t(:objects\n" \
						+ "\t\t{}\n".format("\n\t\t".join(objects)) \
					+ "\t)\n" \
					+ "\t(:init\n" \
						+ "\t\t({})\n".format(")\n\t\t(".join(init_conditions)) \
					+ "\t)\n" \
				+ ")\n"
	
	def generate_knowledge_yaml(self) -> str:
		yaml = "version: 1\nentities:\n"
		for room in self.rooms:
			yaml += room.get_knowledge_yaml(1)
		for item in self.movable_items:
			yaml += item.get_yaml_instance().to_yaml(1)
		return yaml


class Dataset:
	def __init__(self, parent_dir: str) -> None:
		with open(os.path.join(parent_dir, "initial_state.txt")) as f:
			self.initial_state = f.read()
		with open(os.path.join(parent_dir, "domain.pddl")) as f:
			self.domain_pddl = f.read()
		with open(os.path.join(parent_dir, "problem.pddl")) as f:
			self.initial_problem_pddl = f.read()
		with open(os.path.join(parent_dir, "knowledge.yaml")) as f:
			self.initial_knowledge_yaml = f.read()
		
		time_steps = os.listdir(parent_dir)
		time_steps.remove("initial_state.txt")
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
			else:
				curr_data["type"] = "state change"
				with open(os.path.join(curr_dir, "state_change.txt")) as f:
					curr_data["state change"] = f.read()
				with open(os.path.join(curr_dir, "problem.pddl")) as f:
					curr_data["problem pddl"] = f.read()
				with open(os.path.join(curr_dir, "knowledge.yaml")) as f:
					curr_data["knowledge yaml"] = f.read()
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
movable_types = [movable_type for movable_type in movable_types if not isinstance(movable_type, AccompanyingItem)]
stationary_types = get_concrete_subtypes(StationaryItem)
room_types = get_concrete_subtypes(Room)

if __name__ == "__main__":
	generator = DatasetGenerator("test", num_queries=10, state_changes_per_query=10)
	generator.run()