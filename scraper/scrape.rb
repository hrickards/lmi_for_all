require 'csv'
require 'open-uri/cached'
require 'json'
require 'ruby-progressbar'
require 'mongo'
require 'statsample'
include Mongo

PBAR_FORMAT = '%a %B %p%% %t %c/%C'

client = MongoClient.new
db = client['lmi']
coll = db['skills']
coll.drop

def slugify(string)
  string.downcase.strip.gsub(' ', '_').gsub(/[^\w-]/, '').to_sym
end

def soc2onet(soc)
  url = "http://api.lmiforall.org.uk/api/v1/o-net/soc2onet/#{soc}"
  data = JSON.load open(url)
  onets = data["onetCodes"].map { |onet| onet["code"] }

  onets.map { |code| {onet: code, soc: soc} }
end

def get_skills(onet)
  url = "http://api.lmiforall.org.uk/api/v1/o-net/skills/#{onet}"
  data = JSON.load open(url)
  skills = []
  data["scales"].each do |scale|
    raise scale["id"].inspect unless scale["id"] == "LV"
    skills << scale["skills"]
  end
  skills
end

onet_codes = []

pbar = ProgressBar.create(title: "Getting ONET codes", total: CSV.read("socs.csv", headers: true).length, format: PBAR_FORMAT)
CSV.foreach("socs.csv", headers: true) do |row|
  soc = row["unitGroup"]
  onet_codes += soc2onet(soc)
  pbar.increment
  # sleep(0.1)
end

all_skills = []
pbar = ProgressBar.create(title: "Getting skills", total: onet_codes.count, format: PBAR_FORMAT)
onet_codes.each do |datum|
  get_skills(datum[:onet]).each do |skills_raw|
    skills = {}
    skills_raw.each do |skill|
      key = slugify(skill["name"])
      skills[key] = skill["value"]
    end
    skills = Hash[skills]
    skills.merge! datum

    # coll.insert skills
    all_skills << skills
  end
  pbar.increment
end

# Not all skills present
skill_keys = all_skills.map { |s| s.keys }.flatten.uniq.select { |k| k != :onet and k != :soc}.sort
universal_keys = skill_keys.select do |key|
  all_skills.all? { |s| s.include? key }
end
universal_keys.sort!

# Regression to predict all values that aren't present
(skill_keys - universal_keys).each do |key|
  # Data that is there for that key
  available_skills = all_skills.select { |s| s.include? key }

  ds = Hash[universal_keys.map do |k|
    [k.to_s, available_skills.map { |s| s[k] }.to_vector(:scale)]
  end].to_dataset

  y = available_skills.map{|s| s[key]}.to_vector(:scale)
  ds['y'] = y

  mlr = Statsample::Regression.multiple(ds,'y')

  all_skills.each_with_index do |s, i|
    next if s.include? key
    x = universal_keys.map { |k| s[k] }
    y = mlr.process(x).round(2)
    all_skills[i][key] = y
  end

  puts "#{key} R2: #{mlr.r2}"
end

# Check all regressed
skill_keys.each { |k| puts k.inspect unless all_skills.all? { |s| s.include? k } }

all_skills.each do |s|
  d = {
    soc: s[:soc],
    onet: s[:onet],
    data: skill_keys.map { |k| s[k] }
  }
  coll.insert d
end
