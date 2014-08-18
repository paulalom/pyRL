#!/bin/python

import libtcodpy as libtcod
import math
import time
import textwrap

SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50
LIMIT_FPS = 20
ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30
MAP_WIDTH = 80
MAP_HEIGHT = 43 
FOV_ALGO = 0  #default FOV algorithm
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10
BACK_COLOR = libtcod.black
MAX_ROOM_MONSTERS = 3
#sizes and coordinates relevant for the GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT
MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1
MAX_ROOM_ITEMS = 2
INVENTORY_WIDTH = 50
HEAL_AMOUNT = 4
LIGHTNING_DAMAGE = 20
LIGHTNING_RANGE = 5
CONFUSE_NUM_TURNS = 3
CONFUSE_RANGE = 5

libtcod.console_set_custom_font('arial10x10.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'python/libtcod tutorial', False)
con = libtcod.console_new(MAP_WIDTH, MAP_HEIGHT)
libtcod.sys_set_fps(LIMIT_FPS)

color_dark_wall = libtcod.Color(50, 50, 50)
color_light_wall = libtcod.white
color_dark_ground = libtcod.Color(50, 50, 50)
color_light_ground = libtcod.white
fov = True
game_state = 'playing'
player_action = None
#create the list of game messages and their colors, starts empty
game_msgs = []

#########################################################################
###                         Misc Classes                              ###
#########################################################################

class Rect:
   #a rectangle on the map. used to characterize a room.
   def __init__(self, x, y, w, h):
      self.x1 = x
      self.y1 = y
      self.x2 = x + w
      self.y2 = y + h

   def center(self):
      center_x = (self.x1 + self.x2) / 2
      center_y = (self.y1 + self.y2) / 2
      return (center_x, center_y)
    
   def intersect(self, other):
      #returns true if this rectangle intersects with another one
      return (self.x1 <= other.x2 and self.x2 >= other.x1 and self.y1 <= other.y2 and self.y2 >= other.y1)

class Item:

   def __init__(self, use_function=None):
     self.use_function = use_function

   #an item that can be picked up and used.
   def pick_up(self):
      #add to the player's inventory and remove from the map
      if len(inventory) >= 26:
         message('Your inventory is full, cannot pick up ' + self.owner.name + '.', libtcod.red)
      else:
         inventory.append(self.owner)
         objects.remove(self.owner)
         message('You picked up a ' + self.owner.name + '!', libtcod.green)

   def use(self):
      #just call the "use_function" if it is defined
      if self.use_function is None:
         message('The ' + self.owner.name + ' cannot be used.')
      else:
         if self.use_function() != 'cancelled':
            inventory.remove(self.owner)  #destroy after use, unless it was cancelled for some reason

class Fighter:
   #combat-related properties and methods (monster, player, NPC).
   def __init__(self, hp, defense, power, death_function=None):
      self.max_hp = hp
      self.hp = hp
      self.defense = defense
      self.power = power
      self.death_function = death_function

   def take_damage(self, damage):
      #apply damage if possible
      if damage > 0:
         self.hp -= damage
      #check for death. If there's a death function, call it.
      if self.hp <= 0:
         function = self.death_function
         if function is not None:
            function(self.owner)
   
   def heal(self, amount):
      if self.hp >= self.max_hp:
         message('You are already at full health.', libtcod.red)
         return 0
      #heal by the given amount, without going over the maximum
      self.hp += amount
      if self.hp > self.max_hp:
         self.hp = self.max_hp
      return 1

   def attack(self, target):
      #a simple formula for attack damage
      damage = self.power - target.fighter.defense
 
      if damage > 0:
         #make the target take some damage
         message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.', libtcod.white)
         target.fighter.take_damage(damage)
      else:
         message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect!', libtcod.white)



class BasicMonster:
    #AI for a basic monster.
#a basic monster takes its turn. If you can see it, it can see you
   def take_turn(self):
      monster = self.owner
      if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
         #move towards player if far away
         if monster.distance_to(player) >= 2:
            monster.move_towards(player.x, player.y)
 
         #close enough, attack! (if the player is still alive.)
         elif player.fighter.hp > 0:
            monster.fighter.attack(player)
   

class ConfusedMonster:
   #AI for a temporarily confused monster (reverts to previous AI after a while).
   def __init__(self, old_ai, num_turns=CONFUSE_NUM_TURNS):
      self.old_ai = old_ai
      self.num_turns = num_turns
 
   def take_turn(self):
      if self.num_turns > 0:  #still confused...
         #move in a random direction 0 is up-left, 2 is up,right, 8 is down-right
         direction = libtcod.random_get_int(0,0,8)
         if (direction != 4): # 4 is no movement
            self.owner.move(direction%3 -1,direction/3 -1)
         self.num_turns -= 1
 
      else:  #restore the previous AI (this one will be deleted because it's not referenced anymore)
         self.owner.ai = self.old_ai
         message('The ' + self.owner.name + ' is no longer confused!', libtcod.red)


#########################################################################
###                         Tile Class                                ###
#########################################################################

class Tile:
   #a tile of the map and its properties
   def __init__(self, blocked, block_sight = None):
      self.blocked = blocked
      self.explored = False

      #by default, if a tile is blocked, it also blocks sight
      if block_sight is None: block_sight = blocked
      self.block_sight = block_sight


#########################################################################
###                         Map Class                                 ###
#########################################################################

class Map:
   def __init__(self, w, h):
      self.w = w
      self.h = h
      self.tiles = []
   
   def generate_map(self):
 
      #fill map with "unblocked" tiles
      self.tiles = [[ Tile(True)
         for y in range(MAP_HEIGHT) ]
             for x in range(MAP_WIDTH) ]

      rooms = []
      num_rooms = 0

      for r in range(MAX_ROOMS):
         #random width and height
         w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
         h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
         #random position without going out of the boundaries of the map
         x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
         y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
   
         #"Rect" class makes rectangles easier to work with
         new_room = Rect(x, y, w, h)

         #run through the other rooms and see if they intersect with this one
         failed = False
         for other_room in rooms:
            if new_room.intersect(other_room):
               failed = True
               break

         if not failed:
            #this means there are no intersections, so this room is valid

            #"paint" it to the map's tiles
            create_room(new_room)
            place_objects(new_room)

            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()

            if num_rooms == 0:
               #this is the first room, where the player starts at
               player.x = new_x
               player.y = new_y
               npc.x = new_x + 1
               npc.y = new_y + 1
 
            else:
               #all rooms after the first:
               #connect it to the previous room with a tunnel
 
               #center coordinates of previous room
               (prev_x, prev_y) = rooms[num_rooms-1].center()
 
               #draw a coin (random number that is either 0 or 1)
               if libtcod.random_get_int(0, 0, 1) == 1:
                  #first move horizontally, then vertically
                  create_h_tunnel(prev_x, new_x, prev_y)
                  create_v_tunnel(prev_y, new_y, new_x)
               else:
                  #first move vertically, then horizontally
                  create_v_tunnel(prev_y, new_y, prev_x)
                  create_h_tunnel(prev_x, new_x, new_y)
 
            #finally, append the new room to the list
            rooms.append(new_room)
            num_rooms += 1

   def at(self, x, y):
      return self.tiles[x][y]   
      
#########################################################################
###                         Object Class                              ###
#########################################################################

class Object:
   #this is a generic object: the player, a monster, an item, the stairs...
   #it's always represented by a character on screen.
   def __init__(self, x, y, char, name, color, blocks=False, fighter=None, ai=None, item=None):
      self.x = x
      self.y = y
      self.char = char
      self.name = name
      self.color = color
      self.blocks = blocks
      self.fighter = fighter
      self.item = item
      if self.item:  #let the Item component know who owns it
         self.item.owner = self
      if self.fighter:  #let the fighter component know who owns it
         self.fighter.owner = self
      self.ai = ai
      if self.ai:  #let the AI component know who owns it
         self.ai.owner = self
 
   def move(self, dx, dy):
      #move by the given amount
      if not is_blocked(self.x + dx, self.y + dy, map):
            self.x += dx
            self.y += dy
 
   def draw(self, fovMap, fov):
      #set the color and then draw the character that represents this object at its position
      if libtcod.map_is_in_fov(fovMap, self.x, self.y) or not fov:
         libtcod.console_set_default_foreground(con, self.color)
         libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)
   def clear(self):
      #erase the character that represents this object
      libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)

   def distance_to(self, other):
      #return the distance to another object
      dx = other.x - self.x
      dy = other.y - self.y
      return math.sqrt(dx ** 2 + dy ** 2)
 
   def move_towards(self, target_x, target_y):
      #vector from this object to the target, and distance
      dx = target_x - self.x
      dy = target_y - self.y
      distance = math.sqrt(dx ** 2 + dy ** 2)

      #normalize it to length 1 (preserving direction), then round it and
      #convert to integer so the movement is restricted to the map grid
      dx = int(round(dx / distance))
      dy = int(round(dy / distance))
      self.move(dx, dy)

#########################################################################
###                      Functions                                    ###
#########################################################################

def get_names_under_mouse():
   global mouse
 
   #return a string with the names of all objects under the mouse
   (x, y) = (mouse.cx, mouse.cy)
   #create a list with the names of all objects at the mouse's coordinates and in FOV
   names = [obj.name for obj in objects
      if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
   names = ', '.join(names)  #join the names, separated by commas
   return names.capitalize()

def cast_heal():
   #heal the player
   if player.fighter.heal(HEAL_AMOUNT):
      message('Your wounds start to feel better!', libtcod.light_violet)
      return
   else:
      return 'cancelled'

def cast_confuse():
    #find closest enemy in-range and confuse it
    monster = closest_monster(CONFUSE_RANGE)
    if monster is None:  #no enemy found within maximum range
        message('No enemy is close enough to confuse.', libtcod.red)
        return 'cancelled'
    #replace the monster's AI with a "confused" one; after some turns it will restore the old AI
    old_ai = monster.ai
    monster.ai = ConfusedMonster(old_ai)
    monster.ai.owner = monster  #tell the new component who owns it
    message('The eyes of the ' + monster.name + ' look vacant, as he starts to stumble around!', libtcod.light_green)

def handle_keys():
   global fov, fov_recompute, objects, game_state, player_action, key
 
#   key = libtcod.console_wait_for_keypress(True)
   #_console_check_for_keypress()
   if key.vk == libtcod.KEY_ENTER and key.lalt:
      #Alt+Enter: toggle fullscreen
      libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())

   elif key.vk == libtcod.KEY_ESCAPE:
      return 'exit'  #exit game


   if (libtcod.console_is_key_pressed(libtcod.KEY_UP)):
      return player_move_or_attack(0, -1)
   elif (libtcod.console_is_key_pressed(libtcod.KEY_DOWN)):
      return player_move_or_attack(0, 1)
   elif (libtcod.console_is_key_pressed(libtcod.KEY_LEFT)):
      return player_move_or_attack(-1, 0)
   elif (libtcod.console_is_key_pressed(libtcod.KEY_RIGHT)):
      return player_move_or_attack(1, 0)

   if game_state == 'playing':
      if key.vk == libtcod.KEY_CHAR:
         key_char = chr(key.c)
         if key_char == 'w':
            return player_move_or_attack(0, -1)
         elif key_char == 's':
            return player_move_or_attack(0, 1)
         elif key_char == 'a':
            return player_move_or_attack(-1, 0)
         elif key_char == 'd':
            return player_move_or_attack(1,0)
         elif key_char == 'i':
            chosen_item = inventory_menu('Press the key next to an item to use it, or any other to cancel.\n')
            if chosen_item is not None:
               chosen_item.use()
         elif key_char == 'g':
            #pick up an item
            for object in objects:  #look for an item in the player's tile
              if object.x == player.x and object.y == player.y and object.item:
                 object.item.pick_up()
                 break

   if key.vk == libtcod.KEY_CHAR:
      if key.c == ord('m'):
         objects = [npc, player]
         map.generate_map()
         fov_recompute = True
      elif key.c == ord('f'):
         fov = not fov

   return 'didnt-take-turn'

def menu(header, options, width, back_color=libtcod.blue, text_color=libtcod.white):
   if len(options) > 26: raise ValueError('Cannot have a menu with more than 26 options.')

   #calculate total height for the header (after auto-wrap) and one line per option
   header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
   height = len(options) + header_height

   #create an off-screen console that represents the menu's window
   window = libtcod.console_new(width, height)
 
   #print the header, with auto-wrap
   libtcod.console_set_default_background(window, back_color)
   libtcod.console_set_default_foreground(window, text_color)
   libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_SCREEN, libtcod.LEFT, header)

   
   #print all the options
   y = header_height
   letter_index = ord('a')
   for option_text in options:
      text = '(' + chr(letter_index) + ') ' + option_text
      libtcod.console_print_ex(window, 0, y, libtcod.BKGND_SCREEN, libtcod.LEFT, text)
      y += 1
      letter_index += 1

   #blit the contents of "window" to the root console
   x = SCREEN_WIDTH/2 - width/2
   y = SCREEN_HEIGHT/2 - height/2
   libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 1.0) #opacity of fg, bg = 1.0, 1.0

   #present the root console to the player and wait for a key-press
   libtcod.console_flush()
   key = libtcod.console_wait_for_keypress(True)
   
   #convert the ASCII code to an index; if it corresponds to an option, return it
   index = key.c - ord('a')
   if index >= 0 and index < len(options): return index
   return None

def inventory_menu(header):
   #show a menu with each item of the inventory as an option
   if len(inventory) == 0:
      options = ['Inventory is empty.']
   else:
      options = [item.name for item in inventory]
 
   index = menu(header, options, INVENTORY_WIDTH)
   
   #if an item was chosen, return it
   if index is None or len(inventory) == 0: return None
   return inventory[index].item

def player_move_or_attack(dx, dy):
   global fov_recompute
 
   #the coordinates the player is moving to/attacking
   x = player.x + dx
   y = player.y + dy
 
   #try to find an attackable object there
   target = None
   for object in objects:
      if object.fighter and object.x == x and object.y == y:
         target = object
         break
 
   #attack if target found, move otherwise
   if target is not None:
      player.fighter.attack(target)
      return 'attack'
   else:
      player.move(dx, dy)
      fov_recompute = True
      return 'move'


def message(new_msg, color = libtcod.white):
    #split the message if necessary, among multiple lines
    new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)
 
    for line in new_msg_lines:
        #if the buffer is full, remove the first line to make room for the new one
        if len(game_msgs) == MSG_HEIGHT:
            del game_msgs[0]
 
        #add the new line as a tuple, with the text and the color
        game_msgs.append( (line, color) )

def render_all():
   global fov_recompute, fov_map
   #draw all objects in the list
   if fov_recompute:
      #recompute FOV if needed (the player moved or something)
      fov_recompute = False
      libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)

   for y in range(map.h):
      for x in range(map.w):
         if (fov):
            visible = libtcod.map_is_in_fov(fov_map, x, y)
         else:
            visible = True
         wall = map.at(x,y).block_sight
         if not visible:
            if map.at(x,y).explored or not fov:
               if wall:
                  libtcod.console_put_char_ex(con, x, y, '#', color_dark_wall, libtcod.black)
               else:
                  libtcod.console_put_char_ex(con, x, y, '.', color_dark_ground, libtcod.black)
         else: 
            map.at(x,y).explored = True
            if wall:
               libtcod.console_put_char_ex(con, x, y, '#', color_light_wall, BACK_COLOR)
            else:
               libtcod.console_put_char_ex(con, x, y, '.', color_light_ground, BACK_COLOR)
   for object in objects:
      if not object.fighter:
         object.draw(fov_map, fov)
   for object in objects: #combat objects on top
      if object.fighter: # (they cant occupy the same square)
         object.draw(fov_map, fov)
   libtcod.console_blit(con,0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0, 0)
   #prepare to render the GUI panel
   libtcod.console_set_default_background(panel, libtcod.black)
   libtcod.console_clear(panel)
 
   #show the player's stats
   render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp,
      libtcod.light_red, libtcod.darker_red)
   
   #display names of objects under the mouse
   libtcod.console_set_default_foreground(panel, libtcod.light_gray)
   libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())
 
   #blit the contents of "panel" to the root console
   libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)
  

def create_room(room):
   global map
   #go through the tiles in the rectangle and make them passable
   for x in range(room.x1 + 1, room.x2):
      for y in range(room.y1 + 1, room.y2):
         map.at(x,y).blocked = False
         map.at(x,y).block_sight = False

def create_h_tunnel(x1, x2, y):
    global map
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map.at(x,y).blocked = False
        map.at(x,y).block_sight = False

def create_v_tunnel(y1, y2, x):
    global map
    #vertical tunnel
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map.at(x,y).blocked = False
        map.at(x,y).block_sight = False

def place_objects(room):
   #choose random number of monsters
   num_monsters = libtcod.random_get_int(0, 0, MAX_ROOM_MONSTERS)
 
   for i in range(num_monsters):
      #choose random spot for this monster
      x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
      y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
      
      if not is_blocked(x, y,map): 
         if libtcod.random_get_int(0, 0, 100) < 80:  #80% chance of getting an orc
            #create an orc
            fighter_component = Fighter(hp=10, defense=0, power=3, death_function=monster_death)
            ai_component = BasicMonster()
            monster = Object(x, y, 'o', 'orc', libtcod.desaturated_green, blocks=True,fighter=fighter_component,ai=ai_component)
         else:
            #create a troll
            fighter_component = Fighter(hp=16, defense=1, power=4, death_function=monster_death)
            ai_component = BasicMonster()
            monster = Object(x, y, 'T', 'troll', libtcod.darker_green, blocks=True, fighter=fighter_component,ai=ai_component)
 
         objects.append(monster)

     #choose random number of items
   num_items = libtcod.random_get_int(0, 0, MAX_ROOM_ITEMS)
 
   for i in range(num_items):
      #choose random spot for this item
      x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
      y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
 
      #only place it if the tile is not blocked
      if not is_blocked(x, y, map):
         dice = libtcod.random_get_int(0, 0, 100)
         if dice < 70:
            #create a healing potion
            item_component = Item(use_function=cast_heal)
            item = Object(x, y, '!', 'healing potion', libtcod.violet, item=item_component)
         elif dice < 70+15:
            #create a lightning bolt scroll (15% chance)
            item_component = Item(use_function=cast_lightning)
            item = Object(x, y, '?', 'scroll of lightning bolt', libtcod.light_yellow, item=item_component)
         else:
            #create a confuse scroll (15% chance)
            item_component = Item(use_function=cast_confuse)
            item = Object(x, y, '?', 'scroll of confusion', libtcod.light_yellow, item=item_component)
         objects.append(item)

def cast_lightning():
    #find closest enemy (inside a maximum range) and damage it
    monster = closest_monster(LIGHTNING_RANGE)
    if monster is None:  #no enemy found within maximum range
        message('No enemy is close enough to strike.', libtcod.red)
        return 'cancelled'
 
    #zap it!
    message('A lighting bolt strikes the ' + monster.name + ' with a loud thunder! The damage is '
        + str(LIGHTNING_DAMAGE) + ' hit points.', libtcod.light_blue)
    monster.fighter.take_damage(LIGHTNING_DAMAGE)


def closest_monster(max_range):
    #find closest enemy, up to a maximum range, and in the player's FOV
    closest_enemy = None
    closest_dist = max_range + 1  #start with (slightly more than) maximum range
 
    for object in objects:
        if object.fighter and not object == player and libtcod.map_is_in_fov(fov_map, object.x, object.y):
            #calculate distance between this object and the player
            dist = player.distance_to(object)
            if dist < closest_dist:  #it's closer, so remember it
                closest_enemy = object
                closest_dist = dist
    return closest_enemy

def is_blocked(x, y, m):
   #first test the map tile
   if m.at(x,y).blocked:
        return True
   
   #edge of screen test
   if (x < 0 or y < 0 or x >= m.w or y >= m.h):
      return True
 
   #now check for any blocking objects
   for object in objects:
        if object.blocks and object.x == x and object.y == y:
            return True
 
   return False

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
    #render a bar (HP, experience, etc). first calculate the width of the bar
   bar_width = int(float(value) / maximum * total_width)
 
   #render the background first
   libtcod.console_set_default_background(panel, back_color)
   libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)

   #now render the bar on top
   libtcod.console_set_default_background(panel, bar_color)
   if bar_width > 0:
      libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)

   #finally, some centered text with the values
   libtcod.console_set_default_foreground(panel, libtcod.white)
   libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER,
      name + ': ' + str(value) + '/' + str(maximum))

   #print the game messages, one line at a time
   y = 1
   for (line, color) in game_msgs:
      libtcod.console_set_default_foreground(panel, color)
      libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
      y += 1

#########################
#### Death functions ####
#########################

def player_death(player):
   #the game ended!
   global game_state
   message('You died!',libtcod.red)
   game_state = 'dead'
 
   #for added effect, transform the player into a corpse!
   player.char = '%'
   player.color = libtcod.dark_red
 
def monster_death(monster):
   #transform it into a nasty corpse! it doesn't block, can't be
   #attacked and doesn't move
   message(monster.name.capitalize() + ' is dead!', libtcod.orange)
   monster.char = '%'
#   monster.color = libtcod.dark_red
   monster.blocks = False
   monster.fighter = None
   monster.ai = None
   monster.name = 'remains of ' + monster.name


#########################################################################
###                           Main                                    ###
#########################################################################
player_fighter_component = Fighter(hp=30, defense=2, power=5, death_function=player_death)
player = Object(0,0, '@', 'player', libtcod.white, blocks=True, fighter=player_fighter_component)
npc_fighter_component = Fighter(hp=30, defense=2, power=5, death_function=monster_death)
npc = Object(0, 0, '@', 'npc', libtcod.yellow, blocks=True, fighter=npc_fighter_component)
fov = True
objects = [npc, player]
map = Map(MAP_WIDTH,MAP_HEIGHT)
map.generate_map()
fov_map = libtcod.map_new(map.w, map.h)
fov_recompute = True
inventory = []

for y in range(map.h):
   for x in range(map.w):
      libtcod.map_set_properties(fov_map, x, y, not map.at(x,y).block_sight, not map.at(x,y).blocked)

panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)
#welcome message
message('Welcome! Don\'t lose your shoes because its a long walk through the DUNGEON OF HARD STONE FLOORS!', libtcod.red)

mouse = libtcod.Mouse()
key = libtcod.Key()
while not libtcod.console_is_window_closed():
   libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
   render_all()

   libtcod.console_flush()

   for object in objects:
      object.clear()
   
   player_action = handle_keys()
   if player_action == 'exit':
      break
   #let monsters take their turn
   if game_state == 'playing' and player_action != 'didnt-take-turn':
      for object in objects:
         if object.ai:
            object.ai.take_turn()

