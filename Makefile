CXX      = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -pipe -I include
BINDIR   = bin

all: $(BINDIR)/line_gl $(BINDIR)/test_line_gl

$(BINDIR)/line_gl: src/main.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

$(BINDIR)/test_line_gl: src/test.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f $(BINDIR)/line_gl $(BINDIR)/test_line_gl
