import math

# Lots of ugly operator overloading, but it makes the rest of the code prettier.

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

class Pos:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def distance(self, pos):
        dx, dy = pos.x - self.x, pos.y - self.y
        return math.sqrt(dx*dx+dy*dy)
    
    def sqr_distance(self, pos):
        dx, dy = pos.x - self.x, pos.y - self.y
        return max(abs(dx), abs(dy))
    def __add__(self, pos): 
        return Pos(self.x+pos.x, self.y+pos.y)
    def __sub__(self, pos): 
        return Pos(self.x-pos.x, self.y-pos.y)
    def __mul__(self, pos): 
        return Pos(self.x*pos.x, self.y*pos.y)
    def __div__(self, pos): 
        return Pos(float(self.x)/pos.x, float(self.y)/pos.y)
    def __eq__(self, pos):
        if type(self) != type(pos): return False
        return self.x == pos.x and self.y == pos.y
    def __ne__(self, pos):
        return not (self == pos)
    def __str__(self):
        return "Pos(" + str(self.x) + ", " + str(self.y) + ")"
